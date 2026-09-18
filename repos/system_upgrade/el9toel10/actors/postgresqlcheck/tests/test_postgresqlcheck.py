import pytest

from leapp import reporting
from leapp.libraries.actor import postgresqlcheck
from leapp.libraries.actor.postgresqlcheck import (
    _postgresql_conf_uses_plural_socket_param,
    report_installed_packages,
)
from leapp.libraries.common.testutils import create_report_mocked, CurrentActorMocked
from leapp.libraries.stdlib import api
from leapp.models import DistributionSignedRPM, RPM


def _generate_rpm_with_name(name):
    """
    Generate new RPM model item with given name.

    Parameters:
        name (str): rpm name

    Returns:
        rpm  (RPM): new RPM object with name parameter set
    """
    return RPM(name=name,
               version='0.1',
               release='1.sm01',
               epoch='1',
               pgpsig='RSA/SHA256, Mon 01 Jan 1970 00:00:00 AM -03, Key ID 199e2f91fd431d51',
               packager='Red Hat, Inc. <http://bugzilla.redhat.com/bugzilla>',
               arch='noarch')


@pytest.mark.parametrize('has_server', [
    (True),  # with server
    (False),  # without server
])
def test_actor_execution(monkeypatch, has_server):
    """
    Parametrized helper function for test_actor_* functions.

    First generate list of RPM models based on set arguments. Then, run
    the actor fed with our RPM list. Finally, assert Reports
    according to set arguments.

    Parameters:
        has_server  (bool): postgresql-server installed
    """

    # Couple of random packages
    rpms = [_generate_rpm_with_name('sed'),
            _generate_rpm_with_name('htop')]

    if has_server:
        # Add postgresql-server
        rpms += [_generate_rpm_with_name('postgresql-server')]

    curr_actor_mocked = CurrentActorMocked(msgs=[DistributionSignedRPM(items=rpms)])
    monkeypatch.setattr(api, 'current_actor', curr_actor_mocked)
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())
    # Default: no postgresql.conf scan match (covered separately below).
    monkeypatch.setattr(
        postgresqlcheck, '_postgresql_conf_uses_plural_socket_param', lambda: False
    )

    # Executed actor fed with out fake RPMs
    report_installed_packages(_context=api)

    if has_server:
        # Assert for postgresql-server package installed
        assert reporting.create_report.called == 1
    else:
        # Assert for no postgresql packages installed
        assert not reporting.create_report.called


def test_plural_socket_param_report_fires_only_when_server_present(monkeypatch):
    """
    When postgresql-server is installed AND postgresql.conf has the active
    plural form, we expect TWO reports (server-installed + plural-param).
    When postgresql-server is absent, the conf scan must not trigger any
    report - the bug is irrelevant without the server.
    """
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())
    monkeypatch.setattr(
        postgresqlcheck, '_postgresql_conf_uses_plural_socket_param', lambda: True
    )

    # With postgresql-server installed: server report + plural-param report.
    rpms_with_server = [
        _generate_rpm_with_name('sed'),
        _generate_rpm_with_name('postgresql-server'),
    ]
    monkeypatch.setattr(
        api, 'current_actor',
        CurrentActorMocked(msgs=[DistributionSignedRPM(items=rpms_with_server)]),
    )
    report_installed_packages(_context=api)
    assert reporting.create_report.called == 2

    # Reset reports between runs.
    monkeypatch.setattr(reporting, "create_report", create_report_mocked())
    monkeypatch.setattr(
        postgresqlcheck, '_postgresql_conf_uses_plural_socket_param', lambda: True
    )

    # Without postgresql-server, the plural-param report must NOT fire even
    # if a file matching the regex somehow existed.
    rpms_no_server = [_generate_rpm_with_name('sed')]
    monkeypatch.setattr(
        api, 'current_actor',
        CurrentActorMocked(msgs=[DistributionSignedRPM(items=rpms_no_server)]),
    )
    report_installed_packages(_context=api)
    assert not reporting.create_report.called


# Each entry: (postgresql.conf body, expected match boolean, description)
_CONF_BODY_CASES = [
    # The active uncommented line in plural form must be detected.
    ("unix_socket_directories = '/var/run/postgresql, /tmp'\n", True, 'active plural'),
    # Leading whitespace is allowed for PG config syntax.
    ("   unix_socket_directories = '/tmp'\n", True, 'leading whitespace'),
    # Commented-out plural is the default and must NOT trigger.
    ("#unix_socket_directories = '/var/run/postgresql, /tmp'\n", False, 'commented default'),
    # Singular (the form PG 9.2 / postgresql-upgrade actually accepts) - no warning.
    ("unix_socket_directory = '/var/run/postgresql'\n", False, 'singular form'),
    # Plural appearing inside a comment about the parameter shouldn't trigger.
    ("# see unix_socket_directories in the docs\n", False, 'mention in comment'),
    # Empty file.
    ("", False, 'empty file'),
    # Multi-line config with the bad line buried.
    (
        "# header\n"
        "shared_buffers = 128MB\n"
        "unix_socket_directories = '/var/run/postgresql'\n"
        "max_connections = 100\n",
        True,
        'mixed multi-line',
    ),
]


@pytest.mark.parametrize('body,expected,desc', _CONF_BODY_CASES)
def test_postgresql_conf_uses_plural_socket_param(tmp_path, body, expected, desc):
    """
    The conf-scan helper must:
      - return True ONLY for an active (uncommented) "unix_socket_directories"
        line, with or without leading whitespace.
      - return False for commented references, the singular form, missing
        files, and unrelated content. False positives here would inhibit
        upgrades unnecessarily.
    """
    conf = tmp_path / 'postgresql.conf'
    conf.write_text(body)
    assert _postgresql_conf_uses_plural_socket_param(str(conf)) is expected, desc


def test_postgresql_conf_uses_plural_socket_param_missing_file(tmp_path):
    """A non-existent postgresql.conf must NOT raise and must report False."""
    missing = tmp_path / 'does-not-exist' / 'postgresql.conf'
    assert _postgresql_conf_uses_plural_socket_param(str(missing)) is False
