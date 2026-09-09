"""Which workflow stage the actor runs in.

Separate from the unit tests because pinning the stage means reading the tags off
the LOADED actor: phase tags are defined by the repository, not the framework, so
the snactor fixtures are what expose the real classes. Reading them rather than
parsing the source is the point - a tag imported from the wrong module would
satisfy a source-level check and not this one. Keeping it out of
test_removestalesysvlinks.py leaves that file runnable against the framework
alone, which is how every other test_*.py in this repository behaves.
"""
from leapp.snactor.fixture import current_actor_libraries, loaded_leapp_repository  # noqa: F401; pylint: disable=unused-import
from leapp.tags import FinalizationPhaseTag, FirstBootPhaseTag


class TestActorPhase(object):
    """The links have to be gone before the new system boots, and the enable has
    to outlive leapp's own systemd state transition.

    Two distinct failures live here. On FirstBoot the generator has already
    turned the links into units and started the services, so the removal takes
    effect only one boot later - and the conversion's finish stage fails first.
    In Finalization *Main* the ordering against set_systemd_services_state is
    undefined (leapp sorts within a stage by produce/consume edges only, and this
    actor consumes nothing and produces only a Report); when this actor runs
    first its `systemctl enable` is undone by that actor's
    `systemctl disable mariadb.service` a fraction of a second later, leaving the
    unit disabled with its S links already removed. Observed on a real
    conversion:

        21:38:55.163 remove_stale_sysv_links:      systemctl enable  mariadb.service
        21:38:55.891 set_systemd_services_state:   systemctl disable mariadb.service

    Nothing then starts the database at boot. The ticket symptom disappears -
    Plesk's finish stage re-enables and starts it - which is exactly why the end
    state of a converted host is not evidence that this actor worked.

    The tags are read from the loaded actor rather than parsed out of the source:
    the snactor fixtures expose the real tag classes, so a tag imported from the
    wrong module cannot satisfy this.
    """

    def test_runs_after_finalization_main(self, current_actor_libraries):
        assert FinalizationPhaseTag.After in current_actor_libraries.tags

    def test_does_not_run_on_first_boot(self, current_actor_libraries):
        assert FirstBootPhaseTag not in current_actor_libraries.tags
