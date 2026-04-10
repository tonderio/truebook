"""
Kushki SFTP ingestion service.
Downloads monthly liquidation files so the process can run without manual Kushki upload.
"""
import os
import logging
import stat
from dataclasses import dataclass
from typing import List, Optional

import paramiko

from app.config import settings

logger = logging.getLogger(__name__)

MONTH_NAMES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

MONTH_NAMES_EN = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}


@dataclass
class DownloadedFile:
    remote_path: str
    remote_name: str
    local_path: str
    size: int


def is_configured() -> bool:
    return bool(
        settings.KUSHKI_SFTP_HOST
        and settings.KUSHKI_SFTP_USERNAME
        and (settings.KUSHKI_SFTP_PRIVATE_KEY or settings.KUSHKI_SFTP_PRIVATE_KEY_PATH)
    )


def _load_private_key():
    import io
    passphrase = settings.KUSHKI_SFTP_PRIVATE_KEY_PASSPHRASE or None

    loaders_file = [
        paramiko.RSAKey.from_private_key_file,
        paramiko.Ed25519Key.from_private_key_file,
        paramiko.ECDSAKey.from_private_key_file,
    ]
    loaders_str = [
        paramiko.RSAKey.from_private_key,
        paramiko.Ed25519Key.from_private_key,
        paramiko.ECDSAKey.from_private_key,
    ]

    # Prefer key content from env var over file path
    if settings.KUSHKI_SFTP_PRIVATE_KEY:
        key_content = settings.KUSHKI_SFTP_PRIVATE_KEY.replace("\\n", "\n")
        errors = []
        for loader in loaders_str:
            try:
                return loader(io.StringIO(key_content), password=passphrase)
            except Exception as e:
                errors.append(f"{loader.__qualname__}: {e}")
        raise ValueError("Unable to parse SFTP private key from env var. " + " | ".join(errors))

    key_path = settings.KUSHKI_SFTP_PRIVATE_KEY_PATH
    if not key_path:
        raise ValueError("KUSHKI_SFTP_PRIVATE_KEY or KUSHKI_SFTP_PRIVATE_KEY_PATH is required")
    if not os.path.exists(key_path):
        raise ValueError(f"SFTP private key not found at: {key_path}")

    errors = []
    for loader in loaders_file:
        try:
            return loader(key_path, password=passphrase)
        except Exception as e:
            errors.append(f"{loader.__qualname__}: {e}")
    raise ValueError("Unable to parse SFTP private key from file. " + " | ".join(errors))


def _connect() -> paramiko.SFTPClient:
    if not is_configured():
        raise ValueError("Kushki SFTP is not configured")

    pkey = _load_private_key()
    transport = paramiko.Transport((settings.KUSHKI_SFTP_HOST, settings.KUSHKI_SFTP_PORT))
    transport.banner_timeout = settings.KUSHKI_SFTP_TIMEOUT_SECONDS
    transport.connect(username=settings.KUSHKI_SFTP_USERNAME, pkey=pkey)
    return paramiko.SFTPClient.from_transport(transport)


def _month_tokens(year: int, month: int) -> List[str]:
    mm = f"{month:02d}"
    month_name_es = MONTH_NAMES_ES.get(month, "")
    month_name_en = MONTH_NAMES_EN.get(month, "")
    return [
        f"{year}{mm}",
        f"{year}-{mm}",
        f"{year}_{mm}",
        f"{mm}{year}",
        f"{mm}-{year}",
        f"{mm}_{year}",
        f"{month_name_es}_{year}",
        f"{month_name_es}-{year}",
        f"{month_name_es}{year}",
        month_name_es,
        f"{month_name_en}_{year}",
        f"{month_name_en}-{year}",
        f"{month_name_en}{year}",
        month_name_en,
    ]


def _match_month_file(file_path: str, year: int, month: int) -> bool:
    name = file_path.lower()
    if not name.endswith((".xlsx", ".xls", ".csv")):
        return False
    tokens = _month_tokens(year, month)
    return any(token in name for token in tokens)


def _choose_remote_dir(sftp: paramiko.SFTPClient) -> str:
    configured = settings.KUSHKI_SFTP_REMOTE_DIR or "/Mensual"
    candidates = [configured, "/Mensual", "/Diario", "/"]
    for path in candidates:
        try:
            sftp.listdir(path)
            return path
        except Exception:
            continue
    return "/"


def _list_spreadsheet_files_recursive(
    sftp: paramiko.SFTPClient,
    base_dir: str,
    max_depth: int = 6,
    max_nodes: int = 5000,
) -> List[str]:
    files: List[str] = []
    stack = [(base_dir, 0)]
    seen = 0

    while stack and seen < max_nodes:
        path, depth = stack.pop()
        seen += 1
        try:
            entries = sftp.listdir_attr(path)
        except Exception:
            continue

        for entry in entries:
            full = f"{path.rstrip('/')}/{entry.filename}"
            if stat.S_ISDIR(entry.st_mode):
                if depth < max_depth:
                    stack.append((full, depth + 1))
            else:
                lower = entry.filename.lower()
                if lower.endswith((".xlsx", ".xls", ".csv")):
                    files.append(full)
    return files


def list_month_files(year: int, month: int) -> List[str]:
    sftp = _connect()
    try:
        remote_dir = _choose_remote_dir(sftp)
        all_files = _list_spreadsheet_files_recursive(sftp, remote_dir)
        monthly = [p for p in all_files if _match_month_file(p, year, month)]
        if monthly:
            return sorted(monthly)

        # Fallback: if folder is already month-scoped and contains only spreadsheet files.
        spreadsheet = all_files
        if 0 < len(spreadsheet) <= 50:
            logger.warning(
                "No monthly token match on SFTP; using spreadsheet fallback in %s (%s files)",
                remote_dir,
                len(spreadsheet),
            )
            return sorted(spreadsheet)
        return []
    finally:
        transport = sftp.get_channel().get_transport()
        sftp.close()
        if transport:
            transport.close()


def download_month_files(year: int, month: int, local_dir: str) -> List[DownloadedFile]:
    os.makedirs(local_dir, exist_ok=True)
    sftp = _connect()
    downloaded: List[DownloadedFile] = []
    try:
        remote_dir = _choose_remote_dir(sftp)
        all_files = _list_spreadsheet_files_recursive(sftp, remote_dir)
        selected = [p for p in all_files if _match_month_file(p, year, month)]
        if not selected:
            spreadsheet = all_files
            if 0 < len(spreadsheet) <= 50:
                selected = spreadsheet

        for remote_path in sorted(selected):
            name = os.path.basename(remote_path)
            local_name = f"sftp_kushki_{name}"
            local_path = os.path.join(local_dir, local_name)
            sftp.get(remote_path, local_path)
            try:
                size = sftp.stat(remote_path).st_size
            except Exception:
                size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
            downloaded.append(
                DownloadedFile(
                    remote_path=remote_path,
                    remote_name=name,
                    local_path=local_path,
                    size=size,
                )
            )
        return downloaded
    finally:
        transport = sftp.get_channel().get_transport()
        sftp.close()
        if transport:
            transport.close()
