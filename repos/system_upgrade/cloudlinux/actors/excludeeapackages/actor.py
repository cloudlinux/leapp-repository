from leapp.actors import Actor
from leapp.models import InstalledRPM, InstalledControlPanel, PreRemovedRpmPackages
from leapp.tags import FactsPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.detectcontrolpanel import CPANEL_NAME


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
    consumes = (InstalledRPM, InstalledControlPanel,)
    produces = (PreRemovedRpmPackages,)
    tags = (IPUWorkflowTag, FactsPhaseTag.After)

    @run_on_cloudlinux
    def process(self):
        # Only apply this exclusion on cPanel systems
        panel = next(self.consume(InstalledControlPanel), None)
        if not panel or panel.name != CPANEL_NAME:
            return
        
        # Find all installed ea-* packages
        ea_packages = []
        for rpm_pkgs in self.consume(InstalledRPM):
            for pkg in rpm_pkgs.items:
                if pkg.name.startswith('ea-'):
                    ea_packages.append(pkg)
        
        if ea_packages:
            self.log.info('Found {} EA packages to exclude from leapp upgrade: {}'.format(
                len(ea_packages),
                ', '.join([pkg.name for pkg in ea_packages[:10]]) + (' ...' if len(ea_packages) > 10 else '')
            ))
            # Mark these packages as pre-removed with install=False
            # This tells leapp to ignore them completely
            self.produce(PreRemovedRpmPackages(
                items=ea_packages,
                install=False  # Do not reinstall - elevate-cpanel handles EA packages
            ))
        else:
            self.log.debug('No EA packages found to exclude')

