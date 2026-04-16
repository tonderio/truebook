"""
Kushki SFTP ingestion service.

Downloads monthly liquidation files so the process can run without manual
Kushki upload. Uses the generic SFTPConnector base with Kushki-specific
config from settings.

This module preserves the original public API (is_configured, list_month_files,
download_month_files) so processes.py doesn't need changes.
"""
import logging
from typing import List, Optional

from app.config import settings
from app.services.sftp_base import SFTPConfig, SFTPConnector, DownloadedFile

logger = logging.getLogger(__name__)


def _build_config() -> SFTPConfig:
    return SFTPConfig(
        acquirer_name="kushki",
        enabled=settings.KUSHKI_SFTP_ENABLED,
        host=settings.KUSHKI_SFTP_HOST,
        port=settings.KUSHKI_SFTP_PORT,
        username=settings.KUSHKI_SFTP_USERNAME,
        private_key=settings.KUSHKI_SFTP_PRIVATE_KEY,
        private_key_path=settings.KUSHKI_SFTP_PRIVATE_KEY_PATH,
        private_key_passphrase=settings.KUSHKI_SFTP_PRIVATE_KEY_PASSPHRASE,
        remote_dir=settings.KUSHKI_SFTP_REMOTE_DIR,
        timeout_seconds=settings.KUSHKI_SFTP_TIMEOUT_SECONDS,
        strict_host_key=settings.KUSHKI_SFTP_STRICT_HOST_KEY,
    )


class KushkiSFTP(SFTPConnector):
    """Kushki-specific SFTP with Mensual/Diario fallback directories."""

    def _choose_remote_dir(self, sftp) -> str:
        """Kushki uses /Mensual → /Diario → / fallback chain."""
        configured = self.config.remote_dir or "/Mensual"
        candidates = [configured, "/Mensual", "/Diario", "/"]
        for path in candidates:
            try:
                sftp.listdir(path)
                return path
            except Exception:
                continue
        return "/"


_connector: Optional[KushkiSFTP] = None


def _get_connector() -> KushkiSFTP:
    global _connector
    if _connector is None:
        _connector = KushkiSFTP(_build_config())
    return _connector


# ── Public API (backward-compatible with processes.py) ─────────────────

def is_configured() -> bool:
    """Check if Kushki SFTP credentials are present."""
    return _get_connector().is_configured()


def list_month_files(year: int, month: int) -> List[str]:
    """List remote files matching the given month."""
    return _get_connector().list_month_files(year, month)


def download_month_files(
    year: int,
    month: int,
    local_dir: str,
    existing_hashes: Optional[set] = None,
) -> List[DownloadedFile]:
    """Download monthly files from Kushki SFTP."""
    return _get_connector().download_month_files(year, month, local_dir, existing_hashes)
