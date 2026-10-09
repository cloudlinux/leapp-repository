import os

from leapp import reporting
from leapp.libraries.actor import ignoreclstackexcludes as lib
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked, logger_mocked
from leapp.libraries.stdlib import api
from leapp.models import InstalledRPM, RPM, TargetUserSpaceInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_COMMON = os.path.join(_HERE, '..', '..', '..', '..', 'common', 'actors')

# /etc/dnf/dnf.conf on the CloudLinux 9 DirectAdmin QA image, as custombuild writes it.
DA_DNF_CONF = """[main]
gpgcheck=1
installonly_limit=3
clean_requirements_on_remove=True
best=True
skip_if_unavailable=False
exclude=MariaDB-server* apache* bind-chroot* crit-lve* criu-lve* dovecot* exim* httpd* liblsapi* \
mariadb-server* mod_* mysql-community-server* mysql-server* nginx* php* proftpd* pure-ftpd* \
python-criu-lve* python3-criu-lve* sendmail* vsftpd
"""

# What that box has installed of the CloudLinux stack: python3-criu-lve is not among it.
DA_INSTALLED = ('liblsapi', 'liblsapi-devel', 'crit-lve', 'criu-lve', 'criu-lve-devel', 'python-criu-lve')


def _rpm(name):
    return RPM(name=name, epoch='0', packager='CloudLinux Packaging Team', version='1', release='1.el9',
               arch='x86_64', pgpsig='RSA/SHA256, Key ID 8c55a6628608cb71')


def _setup(monkeypatch, tmp_path, conf, installed=DA_INSTALLED):
    etc = tmp_path / 'etc' / 'dnf'
    etc.mkdir(parents=True)
    (etc / 'dnf.conf').write_text(conf)
    msgs = [TargetUserSpaceInfo(path=str(tmp_path), scratch='/var/lib/leapp/scratch', mounts='/var/lib/leapp/mounts'),
            InstalledRPM(items=[_rpm(n) for n in list(installed) + ['bash', 'httpd-filesystem']])]
    monkeypatch.setattr(api, 'current_actor', CurrentActorMocked(src_ver='9.8', dst_ver='10.0', msgs=msgs))
    monkeypatch.setattr(api, 'current_logger', logger_mocked())
    monkeypatch.setattr(reporting, 'create_report', create_report_mocked())
    return etc / 'dnf.conf'


def _excluded(path):
    for line in path.read_text().splitlines():
        if line.startswith('exclude'):
            return line.split('=', 1)[1].split()
    return None


def test_the_directadmin_exclude_line_no_longer_holds_back_the_cloudlinux_stack(monkeypatch, tmp_path):
    """The upgrade copies the host's dnf.conf into the target userspace. There this
    line filtered out every el10 build of crit-lve and python-criu-lve, whose el9
    builds need Python 3.9, so the CloudLinux 9 to 10 transaction check failed on
    every DirectAdmin server running CloudLinux."""
    conf = _setup(monkeypatch, tmp_path, DA_DNF_CONF)

    lib.process()

    excluded = _excluded(conf)
    for pattern in ('crit-lve*', 'criu-lve*', 'liblsapi*', 'python-criu-lve*'):
        assert pattern not in excluded
    assert excluded[:3] == ['MariaDB-server*', 'apache*', 'bind-chroot*']
    assert 'vsftpd' in excluded and 'php*' in excluded and 'mod_*' in excluded


def test_a_pattern_matching_nothing_installed_stays(monkeypatch, tmp_path):
    conf = _setup(monkeypatch, tmp_path, DA_DNF_CONF)

    lib.process()

    assert 'python3-criu-lve*' in _excluded(conf)


def test_what_was_dropped_is_reported(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, DA_DNF_CONF)

    lib.process()

    assert reporting.create_report.called == 1
    report = reporting.create_report.report_fields
    assert report['severity'] == reporting.Severity.INFO
    for pattern in ('crit-lve*', 'criu-lve*', 'liblsapi*', 'python-criu-lve*'):
        assert pattern in report['summary']
    assert 'python3-criu-lve*' not in report['summary']


def test_comma_separated_and_excludepkgs_forms_are_handled(monkeypatch, tmp_path):
    """'dnf config-manager --save' writes the list comma-separated."""
    conf = _setup(monkeypatch, tmp_path, '[main]\nexcludepkgs = liblsapi*, kernel*, criu-lve*\n')

    lib.process()

    assert conf.read_text() == '[main]\nexcludepkgs = kernel*\n'


def test_a_system_without_the_cloudlinux_stack_is_left_alone(monkeypatch, tmp_path):
    conf = _setup(monkeypatch, tmp_path, DA_DNF_CONF, installed=())

    lib.process()

    assert conf.read_text() == DA_DNF_CONF
    assert reporting.create_report.called == 0


def test_an_exclude_in_another_section_is_left_alone(monkeypatch, tmp_path):
    text = '[main]\ngpgcheck=1\n\n[some-repo]\nexclude=liblsapi*\n'
    conf = _setup(monkeypatch, tmp_path, text)

    lib.process()

    assert conf.read_text() == text
    assert reporting.create_report.called == 0


def test_upstream_still_copies_the_host_dnf_conf_where_this_actor_edits_it():
    """This actor edits the copy upstream puts in the target userspace, after the
    userspace is created and before anything there runs dnf. If upstream moves the
    copy, or the creation to another phase, revisit."""
    with open(os.path.join(_COMMON, 'copydnfconfintotargetuserspace', 'libraries',
                           'copydnfconfintotargetuserspace.py')) as fp:
        assert 'dst="/{}"'.format(lib.DNF_CONF) in fp.read()
    with open(os.path.join(_COMMON, 'targetuserspacecreator', 'actor.py')) as fp:
        assert 'TargetTransactionFactsPhaseTag)' in fp.read()
    with open(os.path.join(_COMMON, 'dnftransactioncheck', 'actor.py')) as fp:
        assert 'TargetTransactionChecksPhaseTag' in fp.read()
