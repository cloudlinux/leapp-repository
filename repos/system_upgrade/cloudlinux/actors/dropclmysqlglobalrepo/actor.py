from leapp.actors import Actor
from leapp.libraries.actor import dropclmysqlglobalrepo
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.reporting import Report
from leapp.tags import ApplicationsPhaseTag, IPUWorkflowTag


class DropClMysqlGlobalRepo(Actor):
    """
    Drop the cl-mysql.repo section CloudLinux 10 no longer publishes.

    With mysql.type=auto, Governor on CloudLinux 8 and 9 writes
    cl$releasever/mysqlmeta/mysql-common.repo, whose [cl-mysql] section points
    at mysqlmeta/mysqlglobalrepo - the "upstream substitute" repository. On
    CloudLinux 10 Governor maps auto to mysql84 instead, and cl10 publishes no
    mysqlglobalrepo tree, so after the upgrade that file 404s and every dnf
    command on the machine fails. Nothing else rewrites it: Governor writes the
    file only from 'mysqlgovernor.py --install'.

    This is the stopgap until Governor's own --fix-repo covers the case.
    """

    name = 'drop_cl_mysql_global_repo'
    consumes = ()
    produces = (Report,)
    tags = (ApplicationsPhaseTag.After, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        dropclmysqlglobalrepo.process()
