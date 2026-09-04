import os

import pytest

from leapp import reporting
from leapp.libraries.actor import removestalesysvlinks
from leapp.libraries.common.testutils import create_report_mocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError


def _make_rc_dirs(tmpdir, links):
    """
    Build /etc/rc.d/rc<N>.d trees under tmpdir.

    :param links: mapping of runlevel -> list of link names
    :return: list of the rc directories created
    """
    init_d = tmpdir.mkdir('init.d')
    rc_dirs = []
    for runlevel, names in sorted(links.items()):
        rc_dir = tmpdir.mkdir('rc{}.d'.format(runlevel))
        rc_dirs.append(str(rc_dir))
        for name in names:
            parsed = removestalesysvlinks.parse_link_name(name)
            target = init_d.join(parsed[1] if parsed else name)
            if not target.check():
                target.write('#!/bin/sh\n')
            os.symlink(str(target), str(rc_dir.join(name)))
    return rc_dirs


class TestParseLinkName(object):
    def test_start_link(self):
        # Exactly the shape cl-MariaDB103-server leaves behind.
        assert removestalesysvlinks.parse_link_name('S64mysql') == ('S', 'mysql')

    def test_kill_link(self):
        assert removestalesysvlinks.parse_link_name('K36mysql') == ('K', 'mysql')

    def test_name_with_digits(self):
        assert removestalesysvlinks.parse_link_name('S80postgresql-13') == ('S', 'postgresql-13')

    @pytest.mark.parametrize('name', ['README', 'mysql', 'S6mysql', 'X64mysql', 'S64'])
    def test_not_a_runlevel_link(self, name):
        assert removestalesysvlinks.parse_link_name(name) is None


class TestCollectSysvLinks(object):
    def test_collects_links_and_notes_start_at_boot(self, tmpdir):
        rc_dirs = _make_rc_dirs(tmpdir, {0: ['K36mysql'], 3: ['S64mysql'], 5: ['S64mysql']})
        links, started = removestalesysvlinks.collect_sysv_links(rc_dirs)
        assert sorted(links) == ['mysql']
        assert len(links['mysql']) == 3
        assert started == {'mysql'}

    def test_a_service_with_only_kill_links_does_not_start_at_boot(self, tmpdir):
        rc_dirs = _make_rc_dirs(tmpdir, {0: ['K36mysql'], 6: ['K36mysql']})
        links, started = removestalesysvlinks.collect_sysv_links(rc_dirs)
        assert sorted(links) == ['mysql']
        assert started == set()

    def test_missing_directories_are_not_an_error(self, tmpdir):
        links, started = removestalesysvlinks.collect_sysv_links([str(tmpdir.join('absent'))])
        assert links == {}
        assert started == set()

    def test_plain_files_are_ignored(self, tmpdir):
        rc_dir = tmpdir.mkdir('rc3.d')
        rc_dir.join('S64mysql').write('not a symlink')
        links, _ = removestalesysvlinks.collect_sysv_links([str(rc_dir)])
        assert links == {}


def _write_units(tmpdir, units):
    """Create real unit FILES. units maps filename -> file body (or a symlink target)."""
    unit_dir = tmpdir.mkdir('units')
    for name, body in units.items():
        target = unit_dir.join(name)
        if body.startswith('->'):
            os.symlink(body[2:].strip(), str(target))
        else:
            target.write(body)
    return str(unit_dir)


# The real cl-MariaDB103-server shape: an init script and mariadb.service, no
# mysql.service of its own, the SysV name reached only through the alias.
MARIADB_UNIT = (
    '[Unit]\nDescription=MariaDB database server\n'
    '[Service]\nExecStart=/usr/sbin/mysqld\n'
    '[Install]\nWantedBy=multi-user.target\nAlias=mysql.service\nAlias=mysqld.service\n'
)


class TestScanUnitProviders(object):
    def test_a_unit_provides_its_own_name(self, tmpdir):
        unit_dir = _write_units(tmpdir, {'drwebd.service': '[Unit]\n'})
        assert removestalesysvlinks.scan_unit_providers([unit_dir]) == {
            'drwebd': 'drwebd.service'}

    def test_a_unit_provides_the_names_it_aliases(self, tmpdir):
        # Without this the mysql links are never matched at all and the actor
        # silently does nothing in the one case it exists for.
        unit_dir = _write_units(tmpdir, {'mariadb.service': MARIADB_UNIT})
        providers = removestalesysvlinks.scan_unit_providers([unit_dir])
        assert providers['mysql'] == 'mariadb.service'
        assert providers['mysqld'] == 'mariadb.service'
        assert providers['mariadb'] == 'mariadb.service'

    def test_an_alias_outside_the_install_section_is_not_a_provider(self, tmpdir):
        unit_dir = _write_units(tmpdir, {
            'x.service': '[Unit]\nAlias=notreally.service\n[Install]\nWantedBy=x\n'})
        assert 'notreally' not in removestalesysvlinks.scan_unit_providers([unit_dir])

    def test_an_alias_symlink_resolves_to_its_target(self, tmpdir):
        unit_dir = _write_units(tmpdir, {'mariadb.service': MARIADB_UNIT,
                                         'mysql.service': '-> mariadb.service'})
        assert removestalesysvlinks.scan_unit_providers([unit_dir])['mysql'] == 'mariadb.service'

    def test_a_missing_directory_is_not_an_error(self, tmpdir):
        assert removestalesysvlinks.scan_unit_providers([str(tmpdir.join('absent'))]) == {}

    def test_generator_output_is_never_consulted(self):
        # systemd-sysv-generator writes under /run/systemd, and it writes units
        # made FROM the links this actor removes. Reading those back makes the
        # 'is there a real unit?' test answer yes for every SysV service, which
        # is how the actor came to remove links for services that had no unit
        # and to enable a name that redirected straight back into chkconfig.
        assert not [d for d in removestalesysvlinks.UNIT_DIRS if d.startswith('/run')]


class TestSelectShadowedServices(object):
    def test_selects_a_service_reached_through_an_alias(self):
        links = {'mysql': ['/etc/rc.d/rc3.d/S64mysql']}
        providers = {'mysql': 'mariadb.service', 'mariadb': 'mariadb.service'}
        assert removestalesysvlinks.select_shadowed_services(links, providers) == {
            'mysql': (['/etc/rc.d/rc3.d/S64mysql'], 'mariadb.service')}

    def test_leaves_a_service_with_no_real_unit_alone(self):
        # Without a unit to take over, the init script is the only way that
        # service runs - removing its links would simply stop it starting.
        links = {'drwebd': ['/etc/rc.d/rc3.d/S20drwebd']}
        assert removestalesysvlinks.select_shadowed_services(links, {'mariadb': 'mariadb.service'}) == {}


class TestProcess(object):
    def _setup(self, monkeypatch, tmpdir, links, units, enable_raises=False):
        rc_dirs = _make_rc_dirs(tmpdir, links)
        unit_dir = _write_units(tmpdir, units)
        monkeypatch.setattr(removestalesysvlinks, '_rc_dirs', lambda: rc_dirs)
        monkeypatch.setattr(removestalesysvlinks, 'UNIT_DIRS', [unit_dir])
        self.enabled = []

        def _enable(unit):
            if enable_raises:
                raise CalledProcessError('boom', ['systemctl', 'enable', unit], {})
            self.enabled.append(unit)

        monkeypatch.setattr(removestalesysvlinks.systemd, 'enable_unit', _enable)
        monkeypatch.setattr(api, 'current_logger', logger_mocked())
        monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
        return rc_dirs

    def test_removes_the_links_and_reports(self, monkeypatch, tmpdir):
        rc_dirs = self._setup(monkeypatch, tmpdir,
                              {0: ['K36mysql'], 3: ['S64mysql']},
                              {'mariadb.service': MARIADB_UNIT})
        removestalesysvlinks.process()
        for rc_dir in rc_dirs:
            assert os.listdir(rc_dir) == []
        assert reporting.create_report.called == 1
        assert 'S64mysql' in reporting.create_report.report_fields['summary']

    def test_enables_the_unit_not_the_sysv_name(self, monkeypatch, tmpdir):
        # Enabling 'mysql.service' finds no native unit, reports 'redirecting to
        # systemd-sysv-install' and calls chkconfig, which puts the links back.
        self._setup(monkeypatch, tmpdir, {3: ['S64mysql']},
                    {'mariadb.service': MARIADB_UNIT})
        removestalesysvlinks.process()
        assert self.enabled == ['mariadb.service']

    def test_does_not_enable_for_kill_links_only(self, monkeypatch, tmpdir):
        self._setup(monkeypatch, tmpdir, {0: ['K36mysql']},
                    {'mariadb.service': MARIADB_UNIT})
        removestalesysvlinks.process()
        assert self.enabled == []

    def test_keeps_the_links_when_the_unit_cannot_be_enabled(self, monkeypatch, tmpdir):
        # Removing them after a failed enable would leave the service started by
        # nothing at all, which is worse than the shadowing being fixed.
        rc_dirs = self._setup(monkeypatch, tmpdir, {3: ['S64mysql']},
                              {'mariadb.service': MARIADB_UNIT}, enable_raises=True)
        removestalesysvlinks.process()
        assert os.listdir(rc_dirs[0]) == ['S64mysql']
        assert reporting.create_report.called == 0

    def test_leaves_unshadowed_links_in_place(self, monkeypatch, tmpdir):
        rc_dirs = self._setup(monkeypatch, tmpdir, {3: ['S20drwebd']},
                              {'mariadb.service': MARIADB_UNIT})
        removestalesysvlinks.process()
        assert os.listdir(rc_dirs[0]) == ['S20drwebd']
        assert reporting.create_report.called == 0

    def test_says_nothing_when_there_are_no_links(self, monkeypatch, tmpdir):
        self._setup(monkeypatch, tmpdir, {}, {'mariadb.service': MARIADB_UNIT})
        removestalesysvlinks.process()
        assert reporting.create_report.called == 0


class TestActorPhase(object):
    """The links have to be gone BEFORE the new system boots, not after.

    systemd-sysv-generator runs at every boot and turns a surviving runlevel
    link into a unit, which then starts the service. On a FirstBoot actor the
    generator has already done that by the time the actor runs: the database
    comes up under the generated mysql.service early in the boot, the actor
    removes the links a minute later, and the conversion's finish stage then
    fails on 'systemctl start mariadb.service' against a datadir that is
    already in use. The removal only takes effect on the SECOND boot, which a
    failed finish stage never reaches.

    Observed on a CloudLinux 8 + Plesk conversion: mysqld_safe as PID 1585
    under /system.slice/mysql.service, and

        mariadb.service: Unit process 1585 (mysqld_safe) remains running
        Failed to start MariaDB database server.

    FinalizationPhase runs in the upgrade initramfs against the mounted target
    root, before any boot of the new system. It is where leapp's own
    SetSystemdServicesState applies unit states, for the same reason.
    """

    def _declared_tags(self):
        import ast
        import os
        actor_py = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'actor.py')
        tree = ast.parse(open(actor_py).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    getattr(t, 'id', None) == 'tags' for t in node.targets):
                return {getattr(e, 'id', getattr(e, 'attr', None))
                        for e in getattr(node.value, 'elts', [])}
        raise AssertionError('the actor declares no tags')

    def test_runs_in_finalization(self):
        assert 'FinalizationPhaseTag' in self._declared_tags()

    def test_does_not_run_on_first_boot(self):
        # By then systemd-sysv-generator has already started the service.
        assert 'FirstBootPhaseTag' not in self._declared_tags()
