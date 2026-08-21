from leapp.actors import Actor
from leapp.libraries.actor import pcidevicedrivers
from leapp.models import PCIDevices, RpmTransactionTasks
from leapp.tags import IPUWorkflowTag, FactsPhaseTag


class PCIDeviceDrivers(Actor):
    """
    Handles driver installation for different PCI devices.

    Consumes data from lspci to detect if any bundled RPM driver packages need to be installed.
    """

    name = 'pci_device_drivers'
    consumes = (PCIDevices,)
    produces = (RpmTransactionTasks,)
    tags = (IPUWorkflowTag, FactsPhaseTag)

    def process(self):
        pcidevicedrivers.process()
