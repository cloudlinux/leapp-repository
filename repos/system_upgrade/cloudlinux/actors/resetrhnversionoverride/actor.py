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
            # CLOS-4056: versionOverride is only set/used by the CLN package
            # channel flow. If the system isn't on CLN for packages, leave
            # /etc/sysconfig/rhn/up2date alone - registration metadata there
            # is not ours to touch.
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
