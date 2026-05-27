"""Tests for the abstract :class:`pyntc.devices.base_device.BaseDevice` contract."""

import pytest

from pyntc.devices.base_device import BaseDevice


@pytest.fixture
def base_device():
    return BaseDevice(host="host", username="user", password="pass")


def test_install_mode_raises_not_implemented(base_device):
    with pytest.raises(NotImplementedError):
        _ = base_device.install_mode
