from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = "enc$"


@lru_cache(maxsize=1)
def _fernet():
    keys = [k.strip() for k in (settings.FIELD_ENCRYPTION_KEY or "").split(",") if k.strip()]
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set")
    return MultiFernet([Fernet(k) for k in keys])


def encrypt(value: str) -> str:
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt field; is FIELD_ENCRYPTION_KEY correct?") from exc


class EncryptedTextField(models.TextField):
    """Text stored Fernet-encrypted in the database and plain in Python.

    Encrypted values cannot be filtered on; use it only for secrets such as
    API keys, tokens and device passwords.
    """

    def from_db_value(self, value, expression, connection):
        return value if not value else decrypt(value)

    def to_python(self, value):
        return decrypt(value) if isinstance(value, str) and value else value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return value if not value else encrypt(value)
