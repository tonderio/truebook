"""
Pagsmile / OXXO Pay SFTP ingestion service.

Pagsmile processes cash payments via OXXO. Deposits don't arrive in
real-time — typical delay of 24-72 hours. This can generate temporary
FALTANTE in the last days of the month. Use `source_delay_known=true`
to suppress alerts in those cases.

SFTP exists on Pagsmile's side; pending credentials from Sandy/Pagsmile.
"""
import logging
from app.config import settings
from app.services.sftp_base import SFTPConfig, SFTPConnector

logger = logging.getLogger(__name__)


def _build_config() -> SFTPConfig:
    return SFTPConfig(
        acquirer_name="pagsmile",
        enabled=settings.PAGSMILE_SFTP_ENABLED,
        host=settings.PAGSMILE_SFTP_HOST,
        port=settings.PAGSMILE_SFTP_PORT,
        username=settings.PAGSMILE_SFTP_USERNAME,
        private_key=settings.PAGSMILE_SFTP_PRIVATE_KEY,
        remote_dir=settings.PAGSMILE_SFTP_REMOTE_DIR,
        timeout_seconds=settings.PAGSMILE_SFTP_TIMEOUT_SECONDS,
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
    return _get_connector().list_month_files(year, month)


def download_month_files(year: int, month: int, local_dir: str, existing_hashes=None):
    return _get_connector().download_month_files(year, month, local_dir, existing_hashes)
