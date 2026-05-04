"""
Secure storage for sensitive data like API keys.

Uses Windows DPAPI for encryption on Windows.
Falls back to base64 encoding on other platforms.
"""
import os
import sys
import base64
import json
from pathlib import Path
from typing import Optional, Dict, Any


class SecretStore:
    """
    Secure storage for sensitive configuration values.

    On Windows: Uses DPAPI (CryptProtectData/CryptUnprotectData)
    On other platforms: Uses base64 encoding (not secure, but better than plaintext)
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the secret store.

        Args:
            storage_path: Path to encrypted secrets file
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Default to secrets.json in app data directory
            app_data_dir = os.environ.get('CLIP_APP_DATA_DIR', '.')
            self.storage_path = Path(app_data_dir) / 'secrets.json'

        self._secrets: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load secrets from storage."""
        if not self.storage_path.exists():
            self._secrets = {}
            return

        try:
            with open(self.storage_path, 'rb') as f:
                encrypted_data = f.read()

            decrypted = self._decrypt(encrypted_data)
            self._secrets = json.loads(decrypted)
        except Exception:
            # If we can't load, start fresh
            self._secrets = {}

    def _save(self) -> None:
        """Save secrets to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = json.dumps(self._secrets, indent=2)
        encrypted = self._encrypt(data)

        # Atomic write
        temp_path = self.storage_path.with_suffix('.tmp')
        with open(temp_path, 'wb') as f:
            f.write(encrypted)
        temp_path.replace(self.storage_path)

    def _encrypt(self, data: str) -> bytes:
        """
        Encrypt data using platform-specific method.

        Windows: DPAPI
        Other: base64 (not secure, but obfuscates)
        """
        if sys.platform == 'win32':
            try:
                import win32crypt
                return win32crypt.CryptProtectData(
                    data.encode('utf-8'),
                    None,  # entropy
                    None,  # reserved
                    None,  # prompt struct
                    win32crypt.CRYPTPROTECT_UI_FORBIDDEN
                )
            except ImportError:
                # win32crypt not available, fall back
                pass

        # Fallback: base64 encoding (not secure, but obfuscates)
        return base64.b64encode(data.encode('utf-8'))

    def _decrypt(self, data: bytes) -> str:
        """
        Decrypt data using platform-specific method.

        Windows: DPAPI
        Other: base64
        """
        if sys.platform == 'win32':
            try:
                import win32crypt
                decrypted, _ = win32crypt.CryptUnprotectData(
                    data,
                    None,  # entropy
                    None,  # reserved
                    None,  # prompt struct
                    0     # flags
                )
                return decrypted.decode('utf-8')
            except ImportError:
                pass
            except Exception:
                # Decryption failed, try base64
                pass

        # Fallback: base64 decoding
        return base64.b64decode(data).decode('utf-8')

    def get(self, key: str) -> Optional[str]:
        """
        Get a secret value.

        Args:
            key: Secret key name

        Returns:
            Secret value or None if not found
        """
        return self._secrets.get(key)

    def set(self, key: str, value: str) -> None:
        """
        Set a secret value.

        Args:
            key: Secret key name
            value: Secret value
        """
        self._secrets[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        """
        Delete a secret.

        Args:
            key: Secret key name

        Returns:
            True if deleted, False if not found
        """
        if key in self._secrets:
            del self._secrets[key]
            self._save()
            return True
        return False

    def list_keys(self) -> list:
        """
        List all secret keys (not values).

        Returns:
            List of key names
        """
        return list(self._secrets.keys())

    def clear(self) -> None:
        """Clear all secrets."""
        self._secrets = {}
        self._save()


# Global instance
secret_store = SecretStore()


# Convenience functions
def get_api_key(provider: str = 'deepseek') -> Optional[str]:
    """
    Get API key for a provider.

    Args:
        provider: Provider name (deepseek, openai, etc.)

    Returns:
        API key or None
    """
    return secret_store.get(f'{provider}_api_key')


def set_api_key(provider: str, api_key: str) -> None:
    """
    Set API key for a provider.

    Args:
        provider: Provider name
        api_key: API key value
    """
    secret_store.set(f'{provider}_api_key', api_key)


def delete_api_key(provider: str) -> bool:
    """
    Delete API key for a provider.

    Args:
        provider: Provider name

    Returns:
        True if deleted
    """
    return secret_store.delete(f'{provider}_api_key')
