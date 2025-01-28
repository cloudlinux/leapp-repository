import os

import pytest

from leapp.libraries.actor import pcidevicedrivers as pdd
from leapp.libraries.common.testutils import logger_mocked
from leapp.models import PCIDevice, PCIDevices, RpmTransactionTasks

FAKE_FOLDER = '/FAKE/FOLDER/PATH'
HP_GEN8_DRIVER_RPM = 'kmod-be2net-12.0.0.0-12.el8_8.elrepo.x86_64.rpm'

DEVICES = [
    PCIDevice(
        slot='00:02.0',
        dev_cls='Ethernet controller',
        vendor='Red Hat, Inc.',
        name='Virtio network device',
        pci_id='8086:7020:1af4:1100',
    ),
    PCIDevice(
        slot='00:02.1',
        dev_cls='Ethernet controller',
        vendor='Emulex Corporation',
        name='OneConnect 10Gb NIC (be3)',
        pci_id='1af4:1002:1af4:0005',
    ),
]

TEST_CASES = [
    (['abc.rpm', 'random.file', HP_GEN8_DRIVER_RPM], HP_GEN8_DRIVER_RPM),
]


@pytest.mark.parametrize('rpms,driver_rpm', TEST_CASES)
def test_pci_device_drivers(monkeypatch, rpms, driver_rpm):
    result = []

    def consume_pci_devices_mocked(*models):
        yield PCIDevices(devices=DEVICES)

    monkeypatch.setattr(pdd.api, 'consume', consume_pci_devices_mocked)
    monkeypatch.setattr(pdd.api, 'current_logger', logger_mocked())
    monkeypatch.setattr(pdd.api, 'get_folder_path', lambda _: FAKE_FOLDER)
    monkeypatch.setattr(pdd.os, 'listdir', lambda _: rpms)
    monkeypatch.setattr(pdd.api, 'produce', lambda *models: result.extend(models))

    pdd.process()

    assert result
    assert isinstance(result[0], RpmTransactionTasks)
    assert result[0].local_rpms
    assert result[0].local_rpms == [os.path.join(FAKE_FOLDER, driver_rpm)]
    assert not result[0].to_install
    assert not result[0].to_remove
    assert not result[0].to_keep
