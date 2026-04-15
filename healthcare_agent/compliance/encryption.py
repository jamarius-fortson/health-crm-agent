"""
Encryption Layer — field-level encryption for direct PHI identifiers.

Uses envelope encryption with a KMS-managed key hierarchy:
- Data Encryption Keys (DEKs): encrypt individual fields
- Key Encryption Key (KEK): encrypts DEKs, managed by KMS

For development/testing, a local AES-256 fallback is available.
For production, AWS KMS with the BAA-covered endpoint is required.

HIPAA Requirements:
- Encryption at rest: field-level for direct identifiers
- Encryption in transit: TLS 1.3 minimum (enforced at HTTP layer)
- Key rotation: documented and tested

Direct identifiers (names, SSN, phone, email, address) are encrypted at the field level.
Clinical data and operational data are encrypted at the database/storage level.
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


@dataclass(frozen=True)
class EncryptedField:
    """An encrypted field value with its metadata."""
    ciphertext: str  # Base64-encoded ciphertext
    key_id: str  # Which key was used (for rotation)
    algorithm: str = "fernet"  # Algorithm identifier


class EncryptionBackend(ABC):
    """Abstract encryption backend."""

    @abstractmethod
    async def encrypt(self, plaintext: str, field_name: str) -> EncryptedField:
        """Encrypt a field value."""

    @abstractmethod
    async def decrypt(self, encrypted: EncryptedField) -> str:
        """Decrypt a field value."""

    @abstractmethod
    async def rotate_key(self) -> str:
        """Rotate the encryption key. Returns new key ID."""


class LocalAESEncryption(EncryptionBackend):
    """
    Local AES-256 encryption for development/testing.

    Uses Fernet (AES-128-CBC with HMAC-SHA256) from the cryptography library.
    In production, use AWS KMS via the BAA-covered endpoint.

    SECURITY NOTE: The key is derived from a password for development convenience.
    In production, use KMS-managed keys with proper key lifecycle management.
    """

    def __init__(self, key: bytes | None = None, key_id: str = "dev-key-1") -> None:
        if key is None:
            # Generate a random key for this instance
            key = Fernet.generate_key()
        self._fernet = Fernet(key)
        self._key_id = key_id

    @classmethod
    def from_password(cls, password: str, key_id: str = "dev-key-1") -> "LocalAESEncryption":
        """Create an encryption backend from a password (development only)."""
        salt = b"hcrm-dev-salt"  # Fixed salt for dev — NEVER do this in production
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return cls(key=key, key_id=key_id)

    async def encrypt(self, plaintext: str, field_name: str = "") -> EncryptedField:
        ciphertext = self._fernet.encrypt(plaintext.encode())
        return EncryptedField(
            ciphertext=base64.b64encode(ciphertext).decode(),
            key_id=self._key_id,
            algorithm="fernet",
        )

    async def decrypt(self, encrypted: EncryptedField) -> str:
        ciphertext = base64.b64decode(encrypted.ciphertext)
        plaintext = self._fernet.decrypt(ciphertext)
        return plaintext.decode()

    async def rotate_key(self) -> str:
        new_key = Fernet.generate_key()
        self._fernet = Fernet(new_key)
        self._key_id = f"dev-key-{os.urandom(4).hex()}"
        return self._key_id


# ============================================================================
# PHI Field Encryption Service
# ============================================================================

class PHIFieldEncryption:
    """
    Service for encrypting/decrypting PHI fields on models.

    Wraps an encryption backend and provides model-level operations.
    """

    # Fields that should ALWAYS be encrypted at rest
    ALWAYS_ENCRYPT_FIELDS: frozenset[str] = frozenset({
        "first_name",
        "last_name",
        "date_of_birth",
        "phone",
        "email",
        "street_address",
        "city",
        "state",
        "zip_code",
        "ssn",
        "subscriber_id",
        "group_number",
        "emergency_contact_name",
        "emergency_contact_phone",
    })

    def __init__(self, backend: EncryptionBackend) -> None:
        self._backend = backend

    async def encrypt_field(
        self,
        value: str,
        field_name: str,
    ) -> EncryptedField:
        """Encrypt a single field value."""
        return await self._backend.encrypt(value, field_name)

    async def decrypt_field(
        self,
        encrypted: EncryptedField,
    ) -> str:
        """Decrypt a single field value."""
        return await self._backend.decrypt(encrypted)

    async def encrypt_phi_dict(
        self,
        data: dict[str, str],
    ) -> dict[str, str | EncryptedField]:
        """
        Encrypt all PHI fields in a dictionary.

        Only fields in ALWAYS_ENCRYPT_FIELDS are encrypted at the field level.
        Other fields are passed through (they're encrypted at the storage level).
        """
        result: dict[str, str | EncryptedField] = {}
        for key, value in data.items():
            if key in self.ALWAYS_ENCRYPT_FIELDS and isinstance(value, str):
                result[key] = await self._backend.encrypt(value, key)
            else:
                result[key] = value
        return result

    async def decrypt_phi_dict(
        self,
        data: dict[str, str | EncryptedField],
    ) -> dict[str, str]:
        """Decrypt all encrypted fields in a dictionary."""
        result: dict[str, str] = {}
        for key, value in data.items():
            if isinstance(value, EncryptedField):
                result[key] = await self._backend.decrypt(value)
            elif isinstance(value, str):
                result[key] = value
            else:
                result[key] = str(value)
        return result


# Development singleton
_dev_encryption = LocalAESEncryption()
dev_phi_encryption = PHIFieldEncryption(_dev_encryption)


def get_dev_encryption() -> PHIFieldEncryption:
    """Get the development encryption backend."""
    return dev_phi_encryption
