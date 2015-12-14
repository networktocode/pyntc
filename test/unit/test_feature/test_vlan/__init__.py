from .eos_mock import FakeEOSNative
from .nxos_mock import FakeNXOSNative

mock_mapper = {
    'eos': FakeEOSNative,
    'nxos': FakeNXOSNative,
}