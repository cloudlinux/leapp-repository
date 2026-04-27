"""Detection helpers for CLN (CloudLinux Network / Spacewalk) state.

A system is considered to have CLN *configured* when it has registration
state plus the spacewalk DNF/YUM plugin installed and not explicitly
disabled. Systems that have been migrated to the no-auth (SWNG mirrorlist)
scheme have either:

  - no `/etc/sysconfig/rhn/systemid` (never registered or deregistered),
  - no spacewalk plugin installed (rhn-client-tools >= 3.0.1 removes it), or
  - the plugin's `enabled = 0` in its config.

CLOS-4056: several CloudLinux-specific actors were written when CLN was the
only scheme and assume it is always active. They need to gate their
behavior on `is_cln_configured()` so systems on the no-auth scheme pass
through without bogus inhibitors or crashes.
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


def is_cln_configured():
    """Return True if CLN plumbing is present and not disabled on this system."""
    if not os.path.exists(RHN_SYSTEMID):
        return False

    configs = [p for p in (SPACEWALK_DNF_CONF, SPACEWALK_YUM_CONF) if os.path.exists(p)]
    if not configs:
        return False

    # If any plugin config explicitly disables the plugin, treat as no-auth.
    for conf in configs:
        if _plugin_explicitly_disabled(conf):
            return False

    return True
