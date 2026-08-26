from leapp.actors import Actor
from leapp.libraries.actor import removestalesysvlinks
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.reporting import Report
from leapp.tags import FirstBootPhaseTag, IPUWorkflowTag


class RemoveStaleSysvLinks(Actor):
    """
    Remove SysV runlevel links that shadow a native systemd unit after the upgrade.

    A package can ship both an init script and a systemd unit, and the runlevel
    links chkconfig created on the source system belong to no package at all -
    so nothing removes them during the upgrade. On the target,
    systemd-sysv-generator turns such a link back into an LSB compatibility unit
    that races the real one.

    cl-MariaDB103-server is the case this was written for: it ships
    /etc/rc.d/init.d/mysql on EL9 as well, the EL8 links survive, and MariaDB
    ends up started by mysqld_safe outside mariadb.service - so
    'systemctl start mariadb' fails against a server that is already running,
    and the init script itself is broken on EL9, where log_success_msg no longer
    exists. leapp's own systemd state transition cannot see any of this: it
    works on units, and these are files under /etc/rc.d/rc*.d.

    Links whose service has no native unit on the target are left alone, since
    there the init script is the only way that service runs.
    """

    name = 'remove_stale_sysv_links'
    consumes = ()
    produces = (Report,)
    tags = (FirstBootPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        removestalesysvlinks.process()
