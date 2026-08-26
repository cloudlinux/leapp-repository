import os

import pytest

from leapp import reporting
from leapp.libraries.actor import removestalesysvlinks
from leapp.libraries.common.testutils import create_report_mocked, logger_mocked
from leapp.libraries.stdlib import api, CalledProcessError
from leapp.models import SystemdServiceFile


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


class TestSelectShadowedServices(object):
    def test_selects_a_service_with_a_native_unit(self):
        links = {'mysql': ['/etc/rc.d/rc3.d/S64mysql']}
        service_files = [SystemdServiceFile(name='mariadb.service', state='enabled'),
                         SystemdServiceFile(name='mysql.service', state='alias')]
        selected = removestalesysvlinks.select_shadowed_services(links, service_files)
        assert selected == {'mysql': (['/etc/rc.d/rc3.d/S64mysql'], 'alias')}

    def test_leaves_a_service_with_no_native_unit_alone(self):
        # Without a unit to take over, the init script is the only way that
        # service runs - removing its links would simply stop it starting.
        links = {'drwebd': ['/etc/rc.d/rc3.d/S20drwebd']}
        service_files = [SystemdServiceFile(name='mariadb.service', state='enabled')]
        assert removestalesysvlinks.select_shadowed_services(links, service_files) == {}

    def test_non_service_units_do_not_shadow(self):
        links = {'mysql': ['/etc/rc.d/rc3.d/S64mysql']}
        service_files = [SystemdServiceFile(name='mysql.timer', state='enabled')]
        assert removestalesysvlinks.select_shadowed_services(links, service_files) == {}


class TestProcess(object):
    def _setup(self, monkeypatch, tmpdir, links, service_files, enable_raises=False):
        rc_dirs = _make_rc_dirs(tmpdir, links)
        monkeypatch.setattr(removestalesysvlinks, '_rc_dirs', lambda: rc_dirs)
        monkeypatch.setattr(removestalesysvlinks.systemd, 'get_service_files',
                            lambda: service_files)
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
        rc_dirs = self._setup(
            monkeypatch, tmpdir,
            {0: ['K36mysql'], 3: ['S64mysql']},
            [SystemdServiceFile(name='mysql.service', state='enabled')])
        removestalesysvlinks.process()
        for rc_dir in rc_dirs:
            assert os.listdir(rc_dir) == []
        assert reporting.create_report.called == 1
        assert 'S64mysql' in reporting.create_report.report_fields['summary']

    def test_enables_the_unit_before_taking_the_start_link_away(self, monkeypatch, tmpdir):
        # The SysV link was what started the service at boot; that intent has to
        # move to the native unit or the service silently stops starting.
        self._setup(monkeypatch, tmpdir, {3: ['S64mysql']},
                    [SystemdServiceFile(name='mysql.service', state='disabled')])
        removestalesysvlinks.process()
        assert self.enabled == ['mysql.service']

    def test_does_not_enable_a_unit_that_is_already_enabled(self, monkeypatch, tmpdir):
        self._setup(monkeypatch, tmpdir, {3: ['S64mysql']},
                    [SystemdServiceFile(name='mysql.service', state='enabled')])
        removestalesysvlinks.process()
        assert self.enabled == []

    def test_does_not_enable_for_kill_links_only(self, monkeypatch, tmpdir):
        self._setup(monkeypatch, tmpdir, {0: ['K36mysql']},
                    [SystemdServiceFile(name='mysql.service', state='disabled')])
        removestalesysvlinks.process()
        assert self.enabled == []

    def test_keeps_the_links_when_the_unit_cannot_be_enabled(self, monkeypatch, tmpdir):
        # Removing them after a failed enable would leave the service started by
        # nothing at all, which is worse than the shadowing being fixed.
        rc_dirs = self._setup(
            monkeypatch, tmpdir, {3: ['S64mysql']},
            [SystemdServiceFile(name='mysql.service', state='disabled')],
            enable_raises=True)
        removestalesysvlinks.process()
        assert os.listdir(rc_dirs[0]) == ['S64mysql']
        assert reporting.create_report.called == 0

    def test_leaves_unshadowed_links_in_place(self, monkeypatch, tmpdir):
        rc_dirs = self._setup(
            monkeypatch, tmpdir, {3: ['S20drwebd']},
            [SystemdServiceFile(name='mariadb.service', state='enabled')])
        removestalesysvlinks.process()
        assert os.listdir(rc_dirs[0]) == ['S20drwebd']
        assert reporting.create_report.called == 0

    def test_says_nothing_when_there_are_no_links(self, monkeypatch, tmpdir):
        self._setup(monkeypatch, tmpdir, {},
                    [SystemdServiceFile(name='mariadb.service', state='enabled')])
        removestalesysvlinks.process()
        assert reporting.create_report.called == 0
