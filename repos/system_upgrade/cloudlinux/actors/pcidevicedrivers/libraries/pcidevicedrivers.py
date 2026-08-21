import os

from leapp.libraries.stdlib import api
from leapp.models import PCIDevices, RpmTransactionTasks


def process():
    """
    Main processing function to handle drivers for PCI devices.
    """
    pci_devices = next(api.consume(PCIDevices), None)
    if pci_devices is None:
        api.current_logger().warning('No PCI devices data available.')
        return

    for device in pci_devices.devices:
        api.current_logger().info(
            'Processing device: class {}, vendor {}, name {}'.format(device.dev_cls,
                                                                     device.vendor,
                                                                     device.name))
        if _is_hp_gen8_device(device):
            _process_hp_gen8_nic_driver(device)


def _is_hp_gen8_device(device):
    """
    Check if the device is HP Gen8 NIC.
    """
    return (device.dev_cls == 'Ethernet controller'
            and 'Emulex' in device.vendor
            and 'OneConnect 10Gb NIC' in device.name)


def _process_hp_gen8_nic_driver(device):
    """
    Handle driver installation for HP Gen8 NIC.
    """
    api.current_logger().info('Processing driver update for device: {}'.format(device.name))
    driver_rpm_name = 'kmod-be2net-12.0.0.0-12.el8_8.elrepo.x86_64.rpm'
    _add_local_rpm(driver_rpm_name)


def _add_local_rpm(rpm_name):
    """
    Add a local RPM to the transaction tasks if it exists.
    """
    location = api.get_folder_path('drivers')
    local_rpms = [name for name in os.listdir(location) if name.endswith('.rpm')]

    if rpm_name in local_rpms:
        rpm_real_path = os.path.realpath(os.path.join(location, rpm_name))
        api.produce(RpmTransactionTasks(local_rpms=[rpm_real_path]))
        api.current_logger().info(
            'Produced RpmTransactionTasks for RPM: {}'.format(rpm_real_path))
    else:
        api.current_logger().warning('RPM {} not found in {}'.format(rpm_name, location))
