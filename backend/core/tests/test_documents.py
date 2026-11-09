import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit

Role = m.StaffAssignment.Role
PDF = b"%PDF-1.7\n%test document\n"


def pdf(name="lease.pdf", content=PDF):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class ResidentDocumentTests(APITestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.media = Path(media)
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.staff = make_staff("office", self.condo, Role.STAFF)
        self.officer = make_staff("guard", self.condo, Role.SECURITY)
        self.owner = make_resident("owner", self.unit)
        self.tenant = make_resident("tenant", self.unit)
        self.residency = self.owner.residencies.get()

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def upload(self, user=None, **extra):
        body = {"residency": self.residency.pk, "kind": "ownership", "title": "Title deed", "file": pdf(), **extra}
        return self.as_(user or self.staff).post("/v1/resident-documents/", body, format="multipart")

    def test_management_uploads_and_the_resident_downloads_their_own(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["file_name"], response.data["size"]), ("lease.pdf", len(PDF)))
        self.assertNotIn("file", response.data)
        doc = m.ResidentDocument.objects.get()
        self.assertNotIn("lease", doc.file.name)  # Stored under a random name.

        listed = self.as_(self.owner).get("/v1/resident-documents/")
        self.assertEqual([d["title"] for d in listed.data["results"]], ["Title deed"])
        download = self.as_(self.owner).get(f"/v1/resident-documents/{doc.pk}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), PDF)
        self.assertIn('filename="lease.pdf"', download["Content-Disposition"])
        self.assertEqual(download["Cache-Control"], "private, no-store")

    def test_others_never_see_it(self):
        doc_id = self.upload().data["id"]
        other_condo = make_condo("other")
        stranger = make_staff("stranger", other_condo, Role.ADMIN)
        for user in (self.tenant, self.officer, stranger):  # Same unit, the guard house, another site.
            self.assertEqual(self.as_(user).get("/v1/resident-documents/").data["count"], 0, user)
            self.assertEqual(self.as_(user).get(f"/v1/resident-documents/{doc_id}/download/").status_code, 404, user)
        self.assertEqual(self.upload(stranger).status_code, 403)

    def test_residents_and_officers_cannot_write(self):
        self.assertEqual(self.upload(self.owner).status_code, 403)
        self.assertEqual(self.upload(self.officer).status_code, 403)
        doc_id = self.upload().data["id"]
        self.assertEqual(self.as_(self.owner).delete(f"/v1/resident-documents/{doc_id}/").status_code, 403)

    def test_only_pdf_jpg_png_by_content(self):
        response = self.upload(file=pdf("lease.pdf", b"MZ\x90\x00 not a pdf"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)

    def test_deleting_removes_the_file(self):
        doc_id = self.upload().data["id"]
        path = Path(m.ResidentDocument.objects.get().file.path)
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.as_(self.staff).delete(f"/v1/resident-documents/{doc_id}/").status_code, 204)
        self.assertFalse(path.exists())
