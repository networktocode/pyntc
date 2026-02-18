from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse
from typing import Optional

# Use Hashing algorithms from Nautobot's supported list.
HASHING_ALGORITHMS = {"md5", "sha1", "sha224", "sha384", "sha256", "sha512", "sha3", "blake2", "blake3"}

@dataclass
class FilePullSpec:
    download_url: str
    checksum: str
    file_name: str
    hashing_algorithm: str = "md5"
    file_size: Optional[int] = None # Size in bytes
    username: Optional[str] = None
    token: Optional[str] = None  # Password/Token
    vrf: Optional[str] = None
    ftp_passive: bool = True

    # This field is calculated, so we don't pass it in the constructor
    clean_url: str = field(init=False)
    scheme: str = field(init=False)

    def __post_init__(self):
        # 1. Validate the hashing algorithm choice
        if self.hashing_algorithm.lower() not in HASHING_ALGORITHMS:
            raise ValueError(f"Unsupported algorithm. Choose from: {HASHING_ALGORITHMS}")

        # Parse the url to extract components
        parsed = urlparse(self.download_url)

        # Extract username/password from URL if not already provided as arguments
        if parsed.username and not self.username:
            self.username = parsed.username
        if parsed.password and not self.token:
            self.token = parsed.password

        # 3. Create the 'clean_url' (URL without the credentials)
        # This is what you actually send to the device if using ip http client
        port = f":{parsed.port}" if parsed.port else ""
        self.clean_url = f"{parsed.scheme}://{parsed.hostname}{port}{parsed.path}"
        self.scheme = parsed.scheme

        # Handle query params if they exist (though we're avoiding '?' for Cisco)
        if parsed.query:
            self.clean_url += f"?{parsed.query}"

    @classmethod
    def from_dict(cls, data: dict):
        """Allows users to just pass a dictionary if they prefer."""
        return cls(**data)

    def to_dict(self):
        """Useful for logging or passing to other Nornir tasks."""
        return asdict(self)
