from leapp.libraries.common.config.version import get_major_version

# Which subdirectory of /boot/efi/EFI/ a distribution keeps its EFI content in,
# keyed by the name that appears in /etc/system-release.
_EFI_DIR_BY_DISTRO = {
    'AlmaLinux': 'almalinux',
    'CentOS Linux': 'centos',
    'CentOS Stream': 'centos',
    'Oracle Linux Server': 'redhat',
    'Red Hat Enterprise Linux': 'redhat',
    'Rocky Linux': 'rocky',
    'Scientific Linux': 'redhat',
}

# CloudLinux is the one distribution whose EFI directory changed between major
# versions, because what it is built on changed. CL7 and CL8 are CentOS-based and
# use EFI/centos; CL9 onwards is AlmaLinux-based and uses EFI/almalinux.
_CLOUDLINUX_EFI_DIR_BY_MAJOR = {
    '7': 'centos',
    '8': 'centos',
}
_CLOUDLINUX_EFI_DIR_DEFAULT = 'almalinux'

DEFAULT_EFI_DIR = 'default'


def get_distro_efi_dir(distro, target_major_version):
    """
    Resolve the /boot/efi/EFI/ subdirectory for a distribution.

    :param distro: The name as it appears in /etc/system-release, e.g. 'CloudLinux'.
    :param target_major_version: Major version of the target system, e.g. '10'.
    :return: The subdirectory name, or 'default' when the distribution is unknown.
    """
    if distro == 'CloudLinux':
        major = get_major_version(str(target_major_version))
        return _CLOUDLINUX_EFI_DIR_BY_MAJOR.get(major, _CLOUDLINUX_EFI_DIR_DEFAULT)
    return _EFI_DIR_BY_DISTRO.get(distro, DEFAULT_EFI_DIR)
