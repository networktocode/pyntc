"""Data Models for Pyntc."""

from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

# Use Hashing algorithms from Nautobot's supported list.
HASHING_ALGORITHMS = {"md5", "sha1", "sha224", "sha384", "sha256", "sha512", "sha3", "blake2", "blake3"}

# Supported units for FileCopyModel.file_size, mapped to their multiplier in bytes.
# Conversions use binary units (1 MB = 1024**2 bytes) to match network-device reporting.
FILE_SIZE_UNITS = {
    "bytes": 1,
    "megabytes": 1024**2,
    "gigabytes": 1024**3,
}


@dataclass
class FileCopyModel:
    """Data class to represent the specification for pulling a file from a URL to a network device.

    Args:
        download_url (str): The URL to download the file from. Can include credentials, but it's recommended to use the username and token fields instead for security reasons.
        checksum (str): The expected checksum of the file.
        file_name (str): The name of the file to be saved on the device.
        file_size (int, optional): The expected size of the file. When supplied, ``remote_file_copy`` verifies the target device has room before starting the transfer. When omitted, the pre-transfer space check is skipped (callers can probe the source URL themselves and populate this field). Defaults to ``None``.
        file_size_unit (str, optional): Unit that ``file_size`` is expressed in. One of ``"bytes"``, ``"megabytes"``, ``"gigabytes"``. Only consulted when ``file_size`` is supplied. Defaults to ``"bytes"``.
        hashing_algorithm (str, optional): The hashing algorithm to use for checksum verification. Defaults to "md5".
        timeout (int, optional): The timeout for the download operation in seconds. Defaults to 900.
        username (str, optional): The username for authentication if required by the URL. Optional if credentials are included in the URL.
        token (str, optional): The password or token for authentication if required by the URL. Optional if credentials are included in the URL.
        vrf (str, optional): The VRF to use for the download if the device supports VRFs. Optional.
        ftp_passive (bool, optional): Whether to use passive mode for FTP downloads. Defaults to True.
    """

    download_url: str
    checksum: str
    file_name: str
    file_size: Optional[int] = None
    file_size_unit: str = "bytes"
    hashing_algorithm: str = "md5"
    timeout: int = 900  # Timeout for the download operation in seconds
    username: Optional[str] = None
    token: Optional[str] = None  # Password/Token
    vrf: Optional[str] = None
    ftp_passive: bool = True

    # Computed fields derived from download_url and file_size — not passed to the constructor
    clean_url: str = field(init=False)
    scheme: str = field(init=False)
    hostname: str = field(init=False)
    port: Optional[int] = field(init=False)
    path: str = field(init=False)
    file_size_bytes: Optional[int] = field(init=False)

    def __post_init__(self):
        """Validate the input and prepare the clean URL after initialization."""
        if self.hashing_algorithm.lower() not in HASHING_ALGORITHMS:
            raise ValueError(f"Unsupported algorithm. Choose from: {HASHING_ALGORITHMS}")

        unit = self.file_size_unit.lower()
        if unit not in FILE_SIZE_UNITS:
            raise ValueError(f"Unsupported file_size_unit. Choose from: {sorted(FILE_SIZE_UNITS)}")
        self.file_size_unit = unit

        if self.file_size is None:
            self.file_size_bytes = None
        else:
            if self.file_size < 0:
                raise ValueError("file_size must be a non-negative integer.")
            self.file_size_bytes = self.file_size * FILE_SIZE_UNITS[unit]

        parsed = urlparse(self.download_url)

        # Extract username/password from URL if not already provided as arguments
        if parsed.username and not self.username:
            self.username = parsed.username
        if parsed.password and not self.token:
            self.token = parsed.password

        # Store parsed URL components
        self.scheme = parsed.scheme
        self.hostname = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path

        # Create the 'clean_url' (URL without credentials)
        port_str = f":{parsed.port}" if parsed.port else ""
        self.clean_url = f"{parsed.scheme}://{parsed.hostname}{port_str}{parsed.path}"

        if parsed.query:
            self.clean_url += f"?{parsed.query}"

    @classmethod
    def from_dict(cls, data: dict):
        """Allows users to just pass a dictionary if they prefer."""
        return cls(**data)

    def to_dict(self):
        """Useful for logging or passing to other Nornir tasks."""
        return asdict(self)
