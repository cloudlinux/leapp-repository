from leapp.actors import Actor
import os

from leapp.libraries.common import dnfconfig, mounting
from leapp.tags import FactsPhaseTag, IPUWorkflowTag

class ExcludeEAPackages(Actor):
    """
    Mark EA (EasyApache) packages as pre-removed so leapp ignores them during upgrade.

    EA packages (ea-*) are managed by elevate-cpanel, not by leapp directly.
    elevate-cpanel removes EA packages before leapp runs and restores them after.
    However, if any EA packages remain installed when leapp runs, they can cause
    dependency conflicts during the preupgrade check.

    This actor marks any remaining ea-* packages as pre-removed with install=False,
    which tells leapp to exclude them from upgrade transactions and dependency checks.

    Related: CLOS-3762
    """

    name = "exclude_ea_packages"
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, FactsPhaseTag.Before)

    def process(self):
        # Only apply this exclusion on cPanel systems
        if not os.path.isdir("/usr/local/cpanel"):
            return

        # Exclude all ea-* packages from DNF transactions instead of producing pre-removed packages
        context = mounting.NotIsolatedActions(base_dir='/')
        existing = dnfconfig._get_excluded_pkgs(context, disable_plugins=[])
        if 'ea-*' not in existing:
            dnfconfig._set_excluded_pkgs(context, existing + ['ea-*'], disable_plugins=[])

        return
