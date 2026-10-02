import pytest

from leapp.libraries.actor import efibootorderfix


@pytest.mark.parametrize(
    ('distro', 'target_major', 'expected'),
    [
        # CloudLinux 7 and 8 are CentOS-based and keep their EFI content under
        # /boot/efi/EFI/centos.
        ('CloudLinux', '8', 'centos'),
        # CloudLinux 9 is AlmaLinux-based: a CL 9.7 host has
        # /boot/efi/EFI/almalinux and no centos directory at all. Resolving this
        # to 'centos' made the actor look for a shim that is not there, find
        # nothing, and return - so the boot entry fix silently did nothing.
        ('CloudLinux', '9', 'almalinux'),
        # CloudLinux 10 keeps AlmaLinux's layout. It also stops rewriting
        # /etc/os-release, but /etc/system-release is what this actor reads and
        # the mapping has to hold whichever name it finds there.
        ('CloudLinux', '10', 'almalinux'),
        ('AlmaLinux', '10', 'almalinux'),
        ('CentOS Linux', '8', 'centos'),
        ('CentOS Stream', '9', 'centos'),
        ('Red Hat Enterprise Linux', '9', 'redhat'),
        ('Rocky Linux', '9', 'rocky'),
        ('Oracle Linux Server', '9', 'redhat'),
        ('Scientific Linux', '8', 'redhat'),
        ('Something Else', '9', 'default'),
    ],
)
def test_get_distro_efi_dir(distro, target_major, expected):
    assert efibootorderfix.get_distro_efi_dir(distro, target_major) == expected


def test_cloudlinux_mapping_is_not_constant():
    """The CloudLinux answer must actually depend on the target major version.

    A mapping that returns the same directory for every CloudLinux target is the
    bug this function exists to fix, so pin that it moves.
    """
    assert (
        efibootorderfix.get_distro_efi_dir('CloudLinux', '8')
        != efibootorderfix.get_distro_efi_dir('CloudLinux', '9')
    )
