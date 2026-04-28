"""Shared fixtures for pyntc integration tests."""

import os
import posixpath

import pytest

from pyntc.utils.models import FileCopyModel

from ._helpers import PROTOCOL_URL_VARS

# Each driver's integration test module is mapped to the hashing algorithm
# its device family implements. ``conftest.py`` owns this mapping (rather
# than per-module constants or .env entries) so the user can run every
# driver's integration suite in one ``pytest tests/integration`` invocation
# and each module automatically picks up the algorithm its hardware
# supports. Junos does not implement sha512 — sha256 is typical on SRX /
# MX. EOS and ASA both implement sha512. Extend the map as new drivers get
# integration tests.
_PLATFORM_HASH_ALGOS = {
    "test_eos_device": "sha512",
    "test_asa_device": "sha512",
    "test_jnpr_device": "sha256",
    "test_ios_device": "md5",
    "test_nxos_device": "sha256",
}

# Maps each hashing algorithm to the suffix convention used on the
# per-algorithm checksum env vars (``FILE_CHECKSUM_512`` / ``_256`` /
# ``_MD5``). The user exports one checksum per algorithm once and
# ``_configure_integration_env`` copies the right one into
# ``FILE_CHECKSUM`` before the module runs.
_HASH_ALGO_ENV_SUFFIXES = {"sha512": "512", "sha256": "256", "md5": "MD5"}


@pytest.fixture(scope="module", autouse=True)
def _configure_integration_env(request):
    """Set ``FILE_HASH_ALGO`` / ``FILE_CHECKSUM`` per test module.

    Resolves the module-specific hashing algorithm from
    ``_PLATFORM_HASH_ALGOS``, copies the matching ``FILE_CHECKSUM_<SUFFIX>``
    env var into ``FILE_CHECKSUM``, and restores any prior values when
    the module finishes. Test files not listed in the map are left alone —
    they either carry no hashing dependency or set their own env.
    """
    module_name = request.module.__name__.split(".")[-1]
    algo = _PLATFORM_HASH_ALGOS.get(module_name)
    if algo is None:
        yield
        return

    suffix = _HASH_ALGO_ENV_SUFFIXES.get(algo)
    checksum = os.environ.get(f"FILE_CHECKSUM_{suffix}") if suffix else None

    # Skip the env overwrite entirely when the suffix env var is missing.
    # Otherwise we would pin FILE_HASH_ALGO to the platform's algo while
    # leaving FILE_CHECKSUM inherited from the shell (possibly a different
    # algo's hash) — tests would then fail at verify with a confusing
    # mismatch. Leaving both vars alone lets the user's own pair win, or
    # lets ``build_file_copy_model`` skip cleanly on missing env.
    if checksum is None:
        yield
        return

    prior_algo = os.environ.get("FILE_HASH_ALGO")
    prior_checksum = os.environ.get("FILE_CHECKSUM")

    os.environ["FILE_HASH_ALGO"] = algo
    os.environ["FILE_CHECKSUM"] = checksum

    yield

    if prior_algo is None:
        os.environ.pop("FILE_HASH_ALGO", None)
    else:
        os.environ["FILE_HASH_ALGO"] = prior_algo
    if prior_checksum is None:
        os.environ.pop("FILE_CHECKSUM", None)
    else:
        os.environ["FILE_CHECKSUM"] = prior_checksum


@pytest.fixture(scope="module")
def any_file_copy_model():
    """Return a ``FileCopyModel`` using the first available protocol URL.

    Used by tests that only need a file reference (existence checks, checksum
    verification) without caring about the transfer protocol. Skips if no
    protocol URL / ``FILE_CHECKSUM`` / ``FILE_SIZE`` env vars are set.
    """
    checksum = os.environ.get("FILE_CHECKSUM")
    checksum_algo = os.environ.get("FILE_HASH_ALGO", "sha512")
    file_size = int(os.environ.get("FILE_SIZE", "0"))
    file_size_unit = os.environ.get("FILE_SIZE_UNIT", "bytes")
    for env_var in PROTOCOL_URL_VARS.values():
        url = os.environ.get(env_var)
        if url and checksum and file_size:
            file_name = os.environ.get("FILE_NAME") or posixpath.basename(url.split("?")[0])
            return FileCopyModel(
                download_url=url,
                checksum=checksum,
                file_name=file_name,
                file_size=file_size,
                file_size_unit=file_size_unit,
                hashing_algorithm=checksum_algo,
                timeout=900,
            )
    pytest.skip("No protocol URL / FILE_CHECKSUM / FILE_SIZE environment variables not set")
