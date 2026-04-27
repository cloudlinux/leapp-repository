"""Detection helpers for the CloudLinux Network (CLN) package channel.

CLN has historically combined two concerns:

  1. **Registration / identity** - the system is registered with the CLN
     server (`/etc/sysconfig/rhn/systemid`, JWT token), used for licensing
     and inventory regardless of how packages are delivered.

  2. **Package delivery** - the system pulls CloudLinux packages through
     the spacewalk DNF/YUM plugin against the CLN-side channel
     (`cloudlinux-x86_64-server-N`).

The no-auth (SWNG) transition decouples these. New CL8 and CL9 systems
keep CLN **registration** but no longer use CLN as the **package
channel** - packages come from the SWNG mirrorlist via
`/etc/yum.repos.d/cl.repo` (`cl-channel`) instead. `rhn-client-tools
>= 3.0.1` disables the spacewalk plugin to enforce this.

The CLN-touching actors in this repo only care about the second concern:
they exist to make the CLN package channel work during ELevate. On
systems where the channel has been switched off they should stand down
even though registration may still be present and valid.

CLOS-4056: gate those actors on `is_cln_package_channel_active()`.
"""

import os


RHN_SYSTEMID = '/etc/sysconfig/rhn/systemid'
SPACEWALK_DNF_CONF = '/etc/dnf/plugins/spacewalk.conf'
SPACEWALK_YUM_CONF = '/etc/yum/pluginconf.d/spacewalk.conf'


def _plugin_explicitly_disabled(conf_path):
    try:
        with open(conf_path) as f:
            for line in f:
                stripped = line.strip().lower()
                if not stripped or stripped.startswith('#') or stripped.startswith('['):
                    continue
                if stripped.startswith('enabled') and '=' in stripped:
                    value = stripped.split('=', 1)[1].strip()
                    return value == '0'
    except (OSError, IOError):
        pass
    return False


def is_cln_package_channel_active():
    """Return True when CLN is the active package channel for this system.

    A True result means the spacewalk DNF/YUM plugin is installed, not
    explicitly disabled, and the system has CLN registration state for
    the plugin to authenticate with. A False result means the system is
    either deregistered or has been moved to the no-auth (SWNG) scheme,
    so CLN-targeting actions (channel switch, mirror pinning, version
    overrides) are not meaningful and should be skipped.

    This is a deliberately heuristic check - it asks "is CLN going to
    serve packages here", not "is the system registered with CLN" (the
    two were the same thing pre-no-auth and have since diverged).
    """
    if not os.path.exists(RHN_SYSTEMID):
        return False

    configs = [p for p in (SPACEWALK_DNF_CONF, SPACEWALK_YUM_CONF) if os.path.exists(p)]
    if not configs:
        return False

    for conf in configs:
        if _plugin_explicitly_disabled(conf):
            return False

    return True
