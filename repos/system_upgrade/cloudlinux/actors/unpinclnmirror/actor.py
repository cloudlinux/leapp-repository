import os

from leapp.actors import Actor
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_configured
from leapp.libraries.common.cln_switch import get_target_userspace_path
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag


class UnpinClnMirror(Actor):
    """
    Remove the pinned CLN mirror.
    See the pin_cln_mirror actor for more details.
    """

    name = 'unpin_cln_mirror'
    consumes = ()
    produces = ()
    tags = (IPUWorkflowTag, FirstBootPhaseTag)

    @run_on_cloudlinux
    def process(self):
        if not is_cln_configured():
            # CLOS-4056: pinclnmirror was skipped on no-auth systems, nothing to unpin.
            return

        target_userspace = get_target_userspace_path()

        mirrorlist_path = os.path.join(target_userspace, 'etc/mirrorlist')
        try:
            os.remove(mirrorlist_path)
        except OSError:
            self.log.info('Can\'t remove %s, file does not exist, doing nothing', mirrorlist_path)

        up2date_path = os.path.join(target_userspace, 'etc/sysconfig/rhn/up2date')
        try:
            with open(up2date_path, 'r') as file:
                lines = [
                    line for line in file.readlines() if 'etc/mirrorlist' not in line
                ]
            with open(up2date_path, 'w') as file:
                file.writelines(lines)
        except (OSError, IOError, ValueError):
            self.log.info('Can update %s file, doing nothing', up2date_path)
