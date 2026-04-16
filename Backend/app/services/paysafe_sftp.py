"""
Paysafe SFTP ingestion service.

Paysafe is structurally supported but has no transaction volume today.
When enabled with an empty remote directory, this generates INFO-level
logs (not WARNING) — absence of transactions is a valid state for Paysafe.
"""
import logging
from app.config import settings
from app.services.sftp_base import SFTPConfig, SFTPConnector

logger = logging.getLogger(__name__)


def _build_config() -> SFTPConfig:
    return SFTPConfig(
        acquirer_name="paysafe",
        enabled=settings.PAYSAFE_SFTP_ENABLED,
        host=settings.PAYSAFE_SFTP_HOST,
        port=settings.PAYSAFE_SFTP_PORT,
        username=settings.PAYSAFE_SFTP_USERNAME,
        private_key=settings.PAYSAFE_SFTP_PRIVATE_KEY,
        remote_dir=settings.PAYSAFE_SFTP_REMOTE_DIR,
        # Paysafe: empty dir is valid, don't use fallback
        fallback_max_files=0,
    )


_connector = None


def _get_connector() -> SFTPConnector:
    global _connector
    if _connector is None:
        _connector = SFTPConnector(_build_config())
    return _connector


def is_configured() -> bool:
    return _get_connector().is_configured()


def list_month_files(year: int, month: int):
    files = _get_connector().list_month_files(year, month)
    if not files:
        logger.info("[paysafe] No files found — this is expected (no transaction volume)")
    return files


def download_month_files(year: int, month: int, local_dir: str, existing_hashes=None):
    files = _get_connector().download_month_files(year, month, local_dir, existing_hashes)
    if not files:
        logger.info("[paysafe] No files downloaded — this is expected (no transaction volume)")
    return files
