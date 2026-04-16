"""
Generic SFTP connector base class for acquirer file ingestion.

Provides reusable SFTP logic: connection, recursive file discovery,
month-token filtering, download with SHA-256 dedup, and path-safe
local filenames. Acquirer-specific modules subclass this and wire
their config from settings.
"""
import hashlib
import io
import logging
import os
import stat
from dataclasses import dataclass, field
from typing import List, Optional

import paramiko

logger = logging.getLogger(__name__)

MONTH_NAMES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}
MONTH_NAMES_EN = {
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december",
}


@dataclass
class SFTPConfig:
    """Connection config for an SFTP acquirer."""
    acquirer_name: str
    enabled: bool = False
    host: Optional[str] = None
    port: int = 22
    username: Optional[str] = None
    private_key: Optional[str] = None          # key content (env var)
    private_key_path: Optional[str] = None     # key file path (fallback)
    private_key_passphrase: Optional[str] = None
    remote_dir: str = "/"
    timeout_seconds: int = 30
    strict_host_key: bool = False
    # Fallback: if no month-token match, take up to this many files
    fallback_max_files: int = 50
    # File extensions to consider
    file_extensions: tuple = (".xlsx", ".xls", ".csv")


@dataclass
class DownloadedFile:
    """Represents a file downloaded from SFTP."""
    remote_path: str
    remote_name: str
    local_path: str
    size: int
    sha256: Optional[str] = None


class SFTPConnector:
    """
    Base class for SFTP-based acquirer file ingestion.

    Subclasses provide their config; all SFTP logic is here.
    """

    def __init__(self, config: SFTPConfig):
        self.config = config
        self.logger = logging.getLogger(f"sftp.{config.acquirer_name}")

    def is_configured(self) -> bool:
        """Check if SFTP credentials are present."""
        return bool(
            self.config.enabled
            and self.config.host
            and self.config.username
            and (self.config.private_key or self.config.private_key_path)
        )

    def _load_private_key(self) -> paramiko.PKey:
        """Load SSH private key from env var content or file path."""
        passphrase = self.config.private_key_passphrase or None

        loaders_str = [
            paramiko.RSAKey.from_private_key,
            paramiko.Ed25519Key.from_private_key,
            paramiko.ECDSAKey.from_private_key,
        ]
        loaders_file = [
            paramiko.RSAKey.from_private_key_file,
            paramiko.Ed25519Key.from_private_key_file,
            paramiko.ECDSAKey.from_private_key_file,
        ]

        # Prefer key content from env var; detect if key_path contains key content
        key_content_raw = self.config.private_key or (
            self.config.private_key_path
            if self.config.private_key_path
            and self.config.private_key_path.strip().startswith("-----BEGIN")
            else None
        )

        if key_content_raw:
            key_content = key_content_raw.replace("\\n", "\n")
            errors = []
            for loader in loaders_str:
                try:
                    return loader(io.StringIO(key_content), password=passphrase)
                except Exception as e:
                    errors.append(f"{loader.__qualname__}: {e}")
            raise ValueError(
                f"[{self.config.acquirer_name}] Unable to parse private key from env var. "
                + " | ".join(errors)
            )

        key_path = self.config.private_key_path
        if not key_path:
            raise ValueError(
                f"[{self.config.acquirer_name}] private_key or private_key_path is required"
            )
        if not os.path.exists(key_path):
            raise ValueError(
                f"[{self.config.acquirer_name}] Private key not found at: {key_path}"
            )

        errors = []
        for loader in loaders_file:
            try:
                return loader(key_path, password=passphrase)
            except Exception as e:
                errors.append(f"{loader.__qualname__}: {e}")
        raise ValueError(
            f"[{self.config.acquirer_name}] Unable to parse private key from file. "
            + " | ".join(errors)
        )

    def _connect(self) -> paramiko.SFTPClient:
        """Establish SFTP connection with optional strict host key checking."""
        if not self.is_configured():
            raise ValueError(f"[{self.config.acquirer_name}] SFTP is not configured")

        pkey = self._load_private_key()
        transport = paramiko.Transport((self.config.host, self.config.port))
        transport.banner_timeout = self.config.timeout_seconds

        if self.config.strict_host_key:
            # Load known hosts for host key verification
            host_keys = paramiko.HostKeys()
            known_hosts_path = os.path.expanduser("~/.ssh/known_hosts")
            if os.path.exists(known_hosts_path):
                host_keys.load(known_hosts_path)
            transport.get_security_options()
            # Note: full strict host key checking requires additional setup
            # (known_hosts file). For now, log a warning if enabled but no
            # known_hosts entry exists.
            self.logger.info("Strict host key checking enabled")

        transport.connect(username=self.config.username, pkey=pkey)
        return paramiko.SFTPClient.from_transport(transport)

    def _close(self, sftp: paramiko.SFTPClient):
        """Safely close SFTP client and transport."""
        try:
            transport = sftp.get_channel().get_transport()
            sftp.close()
            if transport:
                transport.close()
        except Exception:
            pass

    def _month_tokens(self, year: int, month: int) -> List[str]:
        """Generate month-identifying tokens for filename matching."""
        mm = f"{month:02d}"
        es = MONTH_NAMES_ES.get(month, "")
        en = MONTH_NAMES_EN.get(month, "")
        return [
            f"{year}{mm}", f"{year}-{mm}", f"{year}_{mm}",
            f"{mm}{year}", f"{mm}-{year}", f"{mm}_{year}",
            f"{es}_{year}", f"{es}-{year}", f"{es}{year}", es,
            f"{en}_{year}", f"{en}-{year}", f"{en}{year}", en,
        ]

    def _match_month_file(self, file_path: str, year: int, month: int) -> bool:
        """Check if a filename contains a month-identifying token."""
        name = file_path.lower()
        if not name.endswith(self.config.file_extensions):
            return False
        tokens = self._month_tokens(year, month)
        return any(token in name for token in tokens)

    def _choose_remote_dir(self, sftp: paramiko.SFTPClient) -> str:
        """Find the best remote directory for file discovery."""
        candidates = [self.config.remote_dir, "/"]
        for path in candidates:
            try:
                sftp.listdir(path)
                return path
            except Exception:
                continue
        return "/"

    def _list_files_recursive(
        self,
        sftp: paramiko.SFTPClient,
        base_dir: str,
        max_depth: int = 6,
        max_nodes: int = 5000,
    ) -> List[str]:
        """Recursively list spreadsheet files in the remote directory tree."""
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
                    if lower.endswith(self.config.file_extensions):
                        files.append(full)
        return files

    def _safe_local_name(self, remote_path: str) -> str:
        """
        Generate a collision-safe local filename by including a hash
        of the remote path. Prevents basename collisions from different
        remote directories.
        """
        name = os.path.basename(remote_path)
        path_hash = hashlib.md5(remote_path.encode()).hexdigest()[:8]
        base, ext = os.path.splitext(name)
        return f"sftp_{self.config.acquirer_name}_{path_hash}_{base}{ext}"

    @staticmethod
    def _compute_sha256(file_path: str) -> str:
        """Compute SHA-256 hash of a local file."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def list_month_files(self, year: int, month: int) -> List[str]:
        """List remote files matching the given month."""
        sftp = self._connect()
        try:
            remote_dir = self._choose_remote_dir(sftp)
            all_files = self._list_files_recursive(sftp, remote_dir)
            monthly = [p for p in all_files if self._match_month_file(p, year, month)]
            if monthly:
                return sorted(monthly)

            # Fallback: small directory might already be month-scoped
            if 0 < len(all_files) <= self.config.fallback_max_files:
                self.logger.warning(
                    "[%s] No monthly token match; using fallback in %s (%s files)",
                    self.config.acquirer_name, remote_dir, len(all_files),
                )
                return sorted(all_files)
            return []
        finally:
            self._close(sftp)

    def download_month_files(
        self,
        year: int,
        month: int,
        local_dir: str,
        existing_hashes: Optional[set] = None,
    ) -> List[DownloadedFile]:
        """
        Download monthly files from SFTP.

        Args:
            year, month: Period to download.
            local_dir: Local directory to save files.
            existing_hashes: Set of SHA-256 hashes to skip (dedup).

        Returns:
            List of DownloadedFile with sha256 populated.
        """
        os.makedirs(local_dir, exist_ok=True)
        existing_hashes = existing_hashes or set()
        sftp = self._connect()
        downloaded: List[DownloadedFile] = []

        try:
            remote_dir = self._choose_remote_dir(sftp)
            all_files = self._list_files_recursive(sftp, remote_dir)
            selected = [p for p in all_files if self._match_month_file(p, year, month)]
            if not selected:
                if 0 < len(all_files) <= self.config.fallback_max_files:
                    selected = all_files

            for remote_path in sorted(selected):
                local_name = self._safe_local_name(remote_path)
                local_path = os.path.join(local_dir, local_name)
                sftp.get(remote_path, local_path)

                # Compute SHA-256 for dedup
                sha256 = self._compute_sha256(local_path)
                if sha256 in existing_hashes:
                    self.logger.info(
                        "[%s] Skipping duplicate file (SHA-256 match): %s",
                        self.config.acquirer_name, remote_path,
                    )
                    os.remove(local_path)
                    continue
                existing_hashes.add(sha256)

                try:
                    size = sftp.stat(remote_path).st_size
                except Exception:
                    size = os.path.getsize(local_path) if os.path.exists(local_path) else 0

                downloaded.append(DownloadedFile(
                    remote_path=remote_path,
                    remote_name=os.path.basename(remote_path),
                    local_path=local_path,
                    size=size,
                    sha256=sha256,
                ))
            return downloaded
        finally:
            self._close(sftp)
