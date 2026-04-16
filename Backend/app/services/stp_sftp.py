"""
STP SFTP ingestion service.

STP is used primarily for processing withdrawals (dispersiones).
SFTP exists on STP's side; pending credentials from Sandy/STP team.
"""
import logging
from app.config import settings
from app.services.sftp_base import SFTPConfig, SFTPConnector

logger = logging.getLogger(__name__)


def _build_config() -> SFTPConfig:
    return SFTPConfig(
        acquirer_name="stp",
        enabled=settings.STP_SFTP_ENABLED,
        host=settings.STP_SFTP_HOST,
        port=settings.STP_SFTP_PORT,
        username=settings.STP_SFTP_USERNAME,
        private_key=settings.STP_SFTP_PRIVATE_KEY,
        remote_dir=settings.STP_SFTP_REMOTE_DIR,
        timeout_seconds=settings.STP_SFTP_TIMEOUT_SECONDS,
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
