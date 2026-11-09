import json
import shutil
import tarfile
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core import backups
from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit, make_user

Role = m.StaffAssignment.Role


@mock.patch("core.tasks.run_backup.delay")
class BackupTests(APITestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=str(root / "media"), BACKUP_ROOT=str(root / "backups")))
        self.backup_root = root / "backups"
        self.condo = make_condo()
        self.other = make_condo("other")
        self.unit = make_unit(self.condo)
        self.root = make_user("root", is_superuser=True, is_staff=True)
        self.admin = make_staff("admin", self.condo, Role.ADMIN)
        self.resident = make_resident("res", self.unit)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_platform_admins_only(self, _):
        for user in (self.admin, self.resident):
            self.assertEqual(self.as_(user).get("/v1/backups/").status_code, 403)
            self.assertEqual(self.as_(user).post("/v1/backups/", {"kind": "platform"}).status_code, 403)

    def test_start_queues_once(self, delay):
        response = self.as_(self.root).post("/v1/backups/", {"kind": "site", "condominium": self.condo.pk})
        self.assertEqual(response.status_code, 202, response.data)
        delay.assert_called_once_with(response.data["id"])
        self.assertEqual(self.client.post("/v1/backups/", {"kind": "site", "condominium": self.condo.pk}).status_code, 409)
        self.assertEqual(self.client.post("/v1/backups/", {"kind": "site"}).status_code, 400)  # Which site?
        self.assertEqual(self.client.post("/v1/backups/", {"kind": "site", "condominium": self.other.pk}).status_code, 202)

    def test_site_export_has_the_sites_records_and_files_but_no_secrets(self, _):
        m.IntegrationAccount.objects.create(condominium=self.condo, provider="shelly", label="Main", shelly_auth_key="SECRET-KEY")
        m.Unit.objects.create(condominium=self.other, floor="09", unit_number="99")
        m.ResidentDocument.objects.create(residency=self.resident.residencies.get(), title="Lease", file_name="lease.pdf",
                                          file=SimpleUploadedFile("lease.pdf", b"%PDF-1.7 lease"))
        backup = backups.start(m.Backup.Kind.SITE, self.condo, user=self.root)
        backup = backups.run(backup.pk)
        self.assertEqual(backup.status, m.Backup.Status.READY, backup.error)
        self.assertEqual(Path(backup.file.path).parent, self.backup_root)  # Never the real backup folder.
        with zipfile.ZipFile(backup.file.path) as zf:
            names = zf.namelist()
            everything = b"".join(zf.read(n) for n in names)
            units = json.loads(zf.read("data/units.json"))
            people = json.loads(zf.read("data/people.json"))
            documents = json.loads(zf.read("data/resident_documents.json"))
        self.assertEqual([u["unit_number"] for u in units], ["12"])  # Not the other site's unit.
        self.assertEqual({p["username"] for p in people}, {"admin", "res"})
        self.assertIn(f"files/{documents[0]['file']}", names)
        self.assertIn("data/units.csv", names)
        self.assertNotIn(b"SECRET-KEY", everything)
        self.assertNotIn(b"pbkdf2", everything)  # No password hashes.

    def test_platform_backup_has_the_database_and_media(self, _):
        m.Facility.objects.create(condominium=self.condo, name="Pool", image=SimpleUploadedFile("pool.jpg", b"\xff\xd8\xff pool"))
        backup = backups.run(backups.start(m.Backup.Kind.PLATFORM, user=self.root).pk)
        self.assertEqual(backup.status, m.Backup.Status.READY, backup.error)
        self.assertEqual(Path(backup.file.path).parent, self.backup_root)
        with tarfile.open(backup.file.path) as tar:
            names = tar.getnames()
            dump = tar.extractfile("database.dump").read(5)
        self.assertEqual(dump, b"PGDMP")
        self.assertTrue(any(n.startswith("media/facilities/") for n in names))

    def test_downloads_are_recorded_and_expired_backups_pruned(self, _):
        backup = backups.run(backups.start(m.Backup.Kind.SITE, self.condo).pk)
        response = self.as_(self.root).get(f"/v1/backups/{backup.pk}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        b"".join(response.streaming_content)
        listed = self.client.get("/v1/backups/").data["results"][0]
        self.assertEqual(listed["downloads"][0]["user_name"], "root")

        path = Path(backup.file.path)
        m.Backup.objects.filter(pk=backup.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(backups.prune(), 1)
        self.assertFalse(path.exists())
