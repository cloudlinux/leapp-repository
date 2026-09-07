from leapp.actors import Actor
from leapp.libraries.actor import removestalesysvlinks
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.reporting import Report
from leapp.tags import FinalizationPhaseTag, IPUWorkflowTag


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
    exists.

    leapp's own systemd state transition does not see the rc links - it works on
    units - but it is not blind to the service, and that decides when this actor
    may run. The EL9 cl-MariaDB103-server %posttrans recreates the
    mysql.service/mysqld.service alias links and enables mariadb.service during
    the RPM transaction; the transition then sees the unit enabled against a
    disable preset and emits to_disable=[mariadb.service]. Applying that disable
    removes the WantedBy link AND both alias symlinks, which is what lets
    systemd-sysv-generator build a mysql.service from the init script at all.

    Links whose service has no real unit on the target are left alone, since
    there the init script is the only way that service runs.

    Runs in FinalizationPhase.After, against the mounted target root before the
    new system has booted. Two separate constraints pin it there:

    - Not FirstBoot: by then the generator has already turned the links into
      units and started the services, so removing them takes effect only one
      boot later, and the conversion's finish stage fails before that boot.
    - Not Finalization *Main*: set_systemd_services_state applies the disable
      above in that stage, and leapp orders actors within a stage only by
      produce/consume edges. This actor consumes nothing and produces only a
      Report, so nothing pins the two relative to each other - and when this one
      runs first, its enable is undone seconds later, leaving the unit disabled
      with its S links already gone and nothing starting the database at boot.
    """

    name = 'remove_stale_sysv_links'
    consumes = ()
    produces = (Report,)
    tags = (FinalizationPhaseTag.After, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        removestalesysvlinks.process()
