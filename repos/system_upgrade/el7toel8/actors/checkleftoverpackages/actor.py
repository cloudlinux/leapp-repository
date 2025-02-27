from leapp.actors import Actor
from leapp.libraries.common.rpms import get_installed_rpms
from leapp.models import (
    LeftoverPackages,
    TransactionCompleted,
    InstalledUnsignedRPM,
    RPM,
)
from leapp.tags import RPMUpgradePhaseTag, IPUWorkflowTag

LEAPP_PACKAGES = [
    "leapp",
    "leapp-repository",
    "snactor",
    "leapp-repository-deps-el8",
    "leapp-deps-el8",
    "python2-leapp",
]

CPANEL_SUFFIX = "cpanel-"


class CheckLeftoverPackages(Actor):
    """
    Check if there are any RHEL 7 packages present after upgrade.

    Actor produces message containing these packages. Message is empty if there are no el7 package left.
    """

    name = 'check_leftover_packages'
    consumes = (TransactionCompleted, InstalledUnsignedRPM)
    produces = (LeftoverPackages,)
    tags = (RPMUpgradePhaseTag, IPUWorkflowTag)

    def skip_leftover_pkg(self, name, unsigned_set):
        # Packages like these are expected to be not updated.
        is_unsigned = name in unsigned_set
        # Packages like these are updated outside of Leapp.
        is_external = name.startswith(CPANEL_SUFFIX)

        return is_unsigned or is_external

    def process(self):
        installed_rpms = get_installed_rpms()
        if not installed_rpms:
            return

        to_remove = LeftoverPackages()
        unsigned = [
            pkg.name
            for pkg in next(
                self.consume(InstalledUnsignedRPM), InstalledUnsignedRPM()
            ).items
        ]
        unsigned_set = set(unsigned + LEAPP_PACKAGES)

        for rpm in installed_rpms:
            rpm = rpm.strip()
            if not rpm:
                continue
            name, version, release, epoch, packager, arch, pgpsig = rpm.split("|")

            if "el7" in release and not self.skip_leftover_pkg(name, unsigned_set):
                to_remove.items.append(
                    RPM(
                        name=name,
                        version=version,
                        epoch=epoch,
                        packager=packager,
                        arch=arch,
                        release=release,
                        pgpsig=pgpsig,
                    )
                )

        self.produce(to_remove)
