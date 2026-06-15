import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


@lru_cache(maxsize=4)
def _fernet(raw_key):
    # Derive a valid 32-byte urlsafe-base64 Fernet key from whatever secret we
    # have. A dedicated FIELD_ENCRYPTION_KEY is preferred; SECRET_KEY is the dev
    # fallback so local setups work with zero extra config.
    digest = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def get_fernet():
    return _fernet(getattr(settings, "FIELD_ENCRYPTION_KEY", "") or settings.SECRET_KEY)


class EncryptedTextField(models.TextField):
    """A TextField whose contents are encrypted at rest with Fernet.

    Note: encryption is non-deterministic, so these fields cannot be used in
    equality/`filter()` lookups — only read back as plaintext after load.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return get_fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            return get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # Stored before encryption was enabled, or the key changed.
            return value
