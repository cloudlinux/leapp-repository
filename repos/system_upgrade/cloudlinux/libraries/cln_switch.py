import os

from leapp.libraries.stdlib import api
from leapp.libraries.stdlib import run
from leapp.libraries.common.config.version import get_target_major_version

SWITCH_BIN = "/usr/sbin/cln-switch-channel"
TARGET_USERSPACE = '/var/lib/leapp/el{}userspace'
CLN_CACHEONLY_MARKER = '/etc/cln_leapp_in_progress'

def get_target_userspace_path():
    """
    Returns the path to the target OS userspace directory.

    Used as a root dir for Leapp-related package operations.
    Modifications performed in this directory are not visible to the host OS.
    """
    return TARGET_USERSPACE.format(get_target_major_version())

def get_cln_cacheonly_flag_path():
    """
    Get the path to the flag file used to prevent the dnf-spacewalk-plugin
    from contacting the CLN server during transaction.

    Effectively forces the plugin to act as if network connectivity was disabled,
    (no matter if it actually is or not), making it use the local cache only.

    If this flag isn't present during the upgrade,
    the plugin would attempt to contact the CLN server and fail due to the lack
    of network connectivity, disrupting the upgrade.

    DNF plugin runs in the target OS userspace, so the flag must be placed there.
    """
    return os.path.join(get_target_userspace_path(), CLN_CACHEONLY_MARKER)

def cln_switch(target):
    """
    Switch the CloudLinux Network channel to the specified target OS.

    Target OS is stored server-side, so the switch is permanent unless changed again.
    For a CL7 to CL8 upgrade, we need to switch to the CL8 channel to
    get served the correct packages.
    """
    switch_cmd = [SWITCH_BIN, "-t", str(target), "-o", "-f"]
    yum_clean_cmd = ["yum", "clean", "all"]
    res = run(switch_cmd)
    api.current_logger().debug('Channel switch result: %s', res)
    res = run(yum_clean_cmd)  # required to update the repolist
    api.current_logger().debug('yum cleanup result: %s', res)
