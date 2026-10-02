from leapp.actors import Actor
from leapp.libraries.actor import repinelsrepofiles
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.tags import ApplicationsPhaseTag, IPUWorkflowTag


class RepinElsRepofiles(Actor):
    """
    Move the ALT-ELS repository files to the target major after the upgrade.

    The els-*-release and alt-common-release packages pin $releasever in their
    repository files at install time: their %post replaces it with
    `rpm -E %{rhel}`. Inside the upgrade transaction that macro still answers
    the source major for every package installed before the target's macros
    are in place, so on a CloudLinux 9 to 10 upgrade php-els.repo and
    alt-common-els.repo were left on el/9 while the python, ruby and nodejs
    files, installed later, got el/10 - and the upgraded system took PHP
    Selector and alt-common updates from the el9 trees.

    Runs once the transaction is done, as refresh_epel does for the same class
    of problem, and touches only the .repo files those packages own.
    """

    name = 'repin_els_repofiles'
    consumes = ()
    produces = ()
    tags = (ApplicationsPhaseTag.After, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        repinelsrepofiles.process()
