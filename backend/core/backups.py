"""Platform backups and per-site data exports (platform admins only).

- A **platform backup** is ``platform-<date>.tar.gz``: ``database.dump`` (``pg_dump -Fc`` of the whole
  database) and ``media/`` (every uploaded file). It restores the whole platform; see the README.
- A **site export** is ``site-<code>-<date>.zip``: one site's records as JSON and CSV, and the files those
  records point to (documents, photos). It is for reading (handover, audit, a PDPA request), not for
  restoring: sites share the database and people can belong to several sites.

Secrets (encrypted credentials, passwords, pass tokens) and face templates are never exported.
"""
import csv
import io
import json
import logging
import os
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import models as dj
from django.db.models import Q
from django.utils import timezone

from . import models as m
from .fields import EncryptedTextField
from .reports import defuse

log = logging.getLogger(__name__)

# Field names never written to an export, whatever the model.
NEVER = {"password", "token", "token_hash", "face_descriptor"}
PEOPLE_FIELDS = ["id", "username", "first_name", "last_name", "email", "phone", "is_active", "date_joined", "last_login"]

# (file name, model, path from the model to the site). People are handled separately.
SITE_TABLES = [
    ("condominium", m.Condominium, "pk"),
    ("blocks", m.Block, "condominium"),
    ("units", m.Unit, "condominium"),
    ("staff_assignments", m.StaffAssignment, "condominium"),
    ("residencies", m.Residency, "unit__condominium"),
    ("resident_documents", m.ResidentDocument, "residency__unit__condominium"),
    ("vehicles", m.Vehicle, "condominium"),
    ("gates", m.AccessGate, "condominium"),
    ("relays", m.RelayController, "gate__condominium"),
    ("lpr_cameras", m.LprCamera, "gate__condominium"),
    ("kiosks", m.Kiosk, "condominium"),
    ("integration_accounts", m.IntegrationAccount, "condominium"),
    ("visitors", m.Visitor, "condominium"),
    ("invitations", m.Invitation, "condominium"),
    ("visits", m.Visit, "condominium"),
    ("intercom_calls", m.IntercomCall, "condominium"),
    ("access_logs", m.AccessLog, "condominium"),
    ("facilities", m.Facility, "condominium"),
    ("bookings", m.Booking, "condominium"),
    ("payment_settings", m.PaymentSettings, "condominium"),
    ("feedback", m.Feedback, "condominium"),
]


def storage():
    return m.Backup._meta.get_field("file").storage


def start(kind, condominium=None, user=None, automatic=False):
    """Create a backup record and queue it. None when the same backup is already waiting or running."""
    busy = m.Backup.objects.filter(kind=kind, condominium=condominium,
                                   status__in=[m.Backup.Status.PENDING, m.Backup.Status.RUNNING])
    if busy.exists():
        return None
    keep = settings.BACKUP_KEEP_DAYS if kind == m.Backup.Kind.PLATFORM else settings.SITE_EXPORT_KEEP_DAYS
    backup = m.Backup.objects.create(kind=kind, condominium=condominium, created_by=user, automatic=automatic,
                                     expires_at=timezone.now() + timedelta(days=keep))
    from .tasks import run_backup

    run_backup.delay(backup.pk)
    return backup


def run(backup_id):
    backup = m.Backup.objects.select_related("condominium").get(pk=backup_id)
    backup.status = m.Backup.Status.RUNNING
    backup.save(update_fields=["status", "updated_at"])
    stamp = timezone.localtime(backup.created_at).strftime("%Y%m%d-%H%M%S")
    if backup.kind == m.Backup.Kind.PLATFORM:
        name, build = f"platform-{stamp}.tar.gz", _platform
    else:
        name, build = f"site-{backup.condominium.code}-{stamp}.zip", lambda path: _site(backup.condominium, path)
    store = storage()
    final = Path(store.path(name))
    final.parent.mkdir(parents=True, exist_ok=True)
    part = final.with_name(final.name + ".part")
    try:
        build(part)
        part.replace(final)
        os.chmod(final, 0o600)
    except Exception as exc:  # Recorded on the backup, so the dashboard shows why.
        part.unlink(missing_ok=True)
        log.exception("Backup %s failed", backup.pk)
        backup.status, backup.error = m.Backup.Status.FAILED, str(exc)[:2000]
    else:
        backup.status, backup.file.name, backup.size = m.Backup.Status.READY, name, final.stat().st_size
    backup.finished_at = timezone.now()
    backup.save()
    return backup


def prune():
    """Delete backups past their expiry (the file goes with the record)."""
    count = 0
    for backup in m.Backup.objects.filter(expires_at__lt=timezone.now()):
        backup.delete()
        count += 1
    return count


# --- Platform backup ------------------------------------------------------------------------------

def _platform(path):
    db = settings.DATABASES["default"]
    with tempfile.TemporaryDirectory(dir=storage().location) as tmp:
        dump = Path(tmp) / "database.dump"
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "-h", db["HOST"], "-p", str(db.get("PORT") or 5432),
             "-U", db["USER"], "-d", db["NAME"], "-f", str(dump)],
            env={**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}, check=True, capture_output=True, timeout=1800,
        )
        with tarfile.open(path, "w:gz") as tar:
            tar.add(dump, arcname="database.dump")
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                tar.add(media, arcname="media")
            _add_text(tar, "README.txt", PLATFORM_README)


def _add_text(tar, name, text):
    data = text.encode()
    info = tarfile.TarInfo(name)
    info.size, info.mtime = len(data), int(timezone.now().timestamp())
    tar.addfile(info, io.BytesIO(data))


PLATFORM_README = """Elix platform backup

database.dump  PostgreSQL custom-format dump of the whole database (pg_restore)
media/         every uploaded file (MEDIA_ROOT)

Restore it with the steps under "Backups" in the project README.
"""


# --- Site export ----------------------------------------------------------------------------------

def _columns(model):
    fields = [f for f in model._meta.concrete_fields if f.name not in NEVER and not isinstance(f, EncryptedTextField)]
    return fields, list(model._meta.many_to_many)


def _value(field, obj):
    value = getattr(obj, field.attname)
    if isinstance(field, dj.FileField):
        return value.name if value else ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _rows(model, queryset, files):
    fields, many = _columns(model)
    if many:
        queryset = queryset.prefetch_related(*[f.name for f in many])
    for obj in queryset.order_by("pk").iterator(chunk_size=2000):
        row = {f.name if not f.is_relation else f.attname: _value(f, obj) for f in fields}
        for f in many:
            row[f.name] = [o.pk for o in getattr(obj, f.name).all()]
        for f in fields:
            if isinstance(f, dj.FileField) and row[f.name]:
                files.add(row[f.name])
        yield row


def _write_table(zf, name, rows):
    """``data/<name>.json`` and ``data/<name>.csv``, written row by row (access logs can be large).

    A ZIP takes one entry at a time, so the CSV is gathered in a temporary file meanwhile."""
    count = 0
    with tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as out_csv:
        with zf.open(f"data/{name}.json", "w") as raw_json:
            out_json = io.TextIOWrapper(raw_json, encoding="utf-8")
            writer = None
            out_json.write("[")
            for row in rows:
                out_json.write(("," if count else "") + "\n" + json.dumps(row, ensure_ascii=False, default=str))
                if writer is None:
                    writer = csv.DictWriter(out_csv, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow({k: defuse(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                                 for k, v in row.items()})
                count += 1
            out_json.write("\n]\n")
            out_json.flush()
            out_json.detach()
        out_csv.seek(0)
        with zf.open(f"data/{name}.csv", "w") as raw_csv:
            raw_csv.write("\ufeff".encode("utf-8"))  # So Excel reads it as UTF-8.
            while chunk := out_csv.read(1 << 16):
                raw_csv.write(chunk.encode("utf-8"))
    return count


def _site(condo, path):
    media = m.ResidentDocument._meta.get_field("file").storage
    files, counts = set(), {}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        people = m.User.objects.filter(Q(residencies__unit__condominium=condo) | Q(staff_assignments__condominium=condo)).distinct()
        counts["people"] = _write_table(zf, "people", (
            {f: (getattr(u, f).isoformat() if hasattr(getattr(u, f), "isoformat") else getattr(u, f)) for f in PEOPLE_FIELDS}
            | {"phone": str(u.phone or "")}
            for u in people.order_by("pk")
        ))
        for name, model, where in SITE_TABLES:
            queryset = model.objects.filter(**{where: condo.pk if where == "pk" else condo})
            counts[name] = _write_table(zf, name, _rows(model, queryset, files))
        missing = []
        for name in sorted(files):
            if media.exists(name):
                zf.write(media.path(name), f"files/{name}")
            else:
                missing.append(name)
        zf.writestr("README.txt", _site_readme(condo, counts, len(files) - len(missing), missing))


def _site_readme(condo, counts, file_count, missing):
    lines = [
        f"Elix site export: {condo.name} ({condo.code})",
        f"Made {timezone.localtime():%Y-%m-%d %H:%M %Z}",
        "",
        "data/<table>.json and .csv  the site's records (ids link the tables; CSV opens in Excel)",
        "files/                      documents and photos the records point to (same paths as their file columns)",
        "",
        "Not included: passwords, device and payment credentials, pass tokens, face templates.",
        "This export is for reading (handover, audit, PDPA). It is not a backup to restore.",
        "",
        "Records:",
        *[f"  {name}: {count}" for name, count in counts.items()],
        f"Files: {file_count}",
    ]
    if missing:
        lines += ["", "Files referenced but no longer on disk:", *[f"  {name}" for name in missing]]
    return "\n".join(lines) + "\n"
