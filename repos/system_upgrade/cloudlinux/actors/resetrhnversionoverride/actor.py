from leapp.actors import Actor
from leapp.libraries.stdlib import api
from leapp.tags import FinalizationPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_package_channel_active


class ResetRhnVersionOverride(Actor):
    """
    Reset the versionOverride value in the RHN up2date config to empty.
    """

    name = 'reset_rhn_version_override'
    consumes = ()
    produces = ()
    tags = (FinalizationPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        if not is_cln_package_channel_active():
            # CLOS-4056: versionOverride only matters when CLN is delivering packages,
            # since the upgrade rewrites it to drive channel selection.
            # On no-auth systems this does not apply.
            return

        up2date_config = '/etc/sysconfig/rhn/up2date'
        try:
            with open(up2date_config, 'r') as f:
                config_data = f.readlines()
        except (OSError, IOError):
            api.current_logger().info(
                "RHN up2date config %s not present; skipping versionOverride reset",
                up2date_config,
            )
            return

        new_data = []
        for line in config_data:
            if line.startswith('versionOverride='):
                new_data.append('versionOverride=\n')
            else:
                new_data.append(line)
        with open(up2date_config, 'w') as f:
            f.writelines(new_data)
