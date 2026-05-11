"""Detection helpers for the CloudLinux Network (CLN) package channel.

CLN has historically combined two concerns:

1. *Registration / identity* - the system is registered with the CLN
server (`/etc/sysconfig/rhn/systemid`, JWT token), used for licensing
regardless of how packages are delivered.

2. *Package delivery* - the system pulls CloudLinux packages
through the spacewalk DNF/YUM plugin against the
CLN-side channel (`cloudlinux-x86_64-server-N`).

The no-auth repository transition decouples these.
New CL8 and CL9 systems keep CLN *registration*,
but no longer use CLN as the *package channel* - packages come from the SWNG mirrorlist
via `/etc/yum.repos.d/cl.repo` (`cl-channel`) instead.
`rhn-client-tools >= 3.0.1` disables the spacewalk plugin to enforce this.

The CLN-touching actors in this repo only care about the second concern:
they exist to make the CLN package channel work during ELevate.
On systems where the channel has been switched off they should stand down,
regardless of registration state.

CLOS-4056: gate those actors on `is_cln_package_channel_active()`.
"""

import os

from leapp.libraries.stdlib import CalledProcessError, run


RHN_SYSTEMID = '/etc/sysconfig/rhn/systemid'
SPACEWALK_DNF_CONF = '/etc/dnf/plugins/spacewalk.conf'
SPACEWALK_YUM_CONF = '/etc/yum/pluginconf.d/spacewalk.conf'

# Packages that ship the spacewalk-protocol DNF/YUM plugin. Any one of
# them being installed is sufficient evidence that CLN may serve
# packages here; if none of them are present the plugin cannot run, no
# matter what config files happen to be lying around (see
# _spacewalk_plugin_installed below).
_SPACEWALK_PLUGIN_PKGS = (
    'dnf-plugin-spacewalk',
    'python3-dnf-plugin-spacewalk',
    'yum-rhn-plugin',
)


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


def _spacewalk_plugin_installed():
    """True iff at least one spacewalk-protocol plugin package is installed.

    Done via `rpm -q --quiet <pkg>` per package: rpm returns 0 only when
    *that* package is installed. We OR across the candidate names and
    return on the first hit. Errors invoking rpm itself (broken database,
    PATH issues) are treated as "not installed" - a false negative here
    only causes CLN-related actors to stand down, which is the safe side
    of the call.
    """
    for pkg in _SPACEWALK_PLUGIN_PKGS:
        try:
            run(['rpm', '-q', '--quiet', pkg])
            return True
        except CalledProcessError:
            continue
        except (OSError, IOError):
            return False
    return False


def is_cln_package_channel_active():
    """Return True when CLN is the active package channel for this system.

    Requires all of:

    * `/etc/sysconfig/rhn/systemid` present (CLN registration state),
    * at least one spacewalk-protocol plugin package installed,
    * a spacewalk plugin config file present, and
    * none of the present plugin config files explicitly setting `enabled = 0`.

    A False result means the system is either deregistered, has no
    spacewalk plugin installed, or has been moved to the no-auth (SWNG)
    scheme, so CLN-targeting actions (channel switch, mirror pinning,
    version overrides) are not meaningful and should be skipped.

    This is a deliberately heuristic check - it asks "is CLN going to
    serve packages here", not "is the system registered with CLN" (the
    two were the same thing pre-no-auth and have since diverged).

    The plugin-package check guards against stale-config edge cases: when
    rhn-client-tools 3.0+ Obsoletes dnf-plugin-spacewalk, a leftover
    /etc/dnf/plugins/spacewalk.conf (saved without the .rpmsave suffix,
    or manually preserved) would otherwise make the helper claim CLN is
    active when no plugin can actually run.
    """
    if not os.path.exists(RHN_SYSTEMID):
        return False

    if not _spacewalk_plugin_installed():
        return False

    configs = [p for p in (SPACEWALK_DNF_CONF, SPACEWALK_YUM_CONF) if os.path.exists(p)]
    if not configs:
        return False

    for conf in configs:
        if _plugin_explicitly_disabled(conf):
            return False

    return True
