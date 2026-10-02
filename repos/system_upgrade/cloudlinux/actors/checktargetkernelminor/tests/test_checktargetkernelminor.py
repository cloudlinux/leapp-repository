"""Unit tests for the checktargetkernelminor library.

The actor itself is a thin wrapper around ``library.process(installroot)``;
the interesting logic - parsing the minor out of RPM version/release strings
and comparing the highest available kernel minor against the highest
available cloudlinux-release minor - lives in the library, so that is what
gets exercised here.
"""

import pytest

from leapp.libraries.actor import checktargetkernelminor as lib
from leapp.libraries.common.testutils import CurrentActorMocked, logger_mocked


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParseKernelMinor:
    """Extract the minor from a kernel RPM release field (`...elN_M...`),
    requiring the major to match the target.  Cross-major rows must not be
    conflated - the target userspace's repoquery returns both source and
    target packages, and only the target major's minors are meaningful.
    """

    @pytest.mark.parametrize(
        ('release', 'target_major', 'expected'),
        [
            # The customer's exact case (CLOS-3716), target=9:
            ('611.5.1.el9_7', '9', 7),
            ('570.12.1.el9_6', '9', 6),
            ('570.62.1.el9_6', '9', 6),
            # Vendor suffix appended after the dist tag must not break parsing:
            ('1.0-1.el8_6.cloudlinux', '8', 6),
            # el8_10 must parse correctly for el7->el8 path:
            ('1.0-1.el8_10', '8', 10),
            ('1.0-1.el8_8', '8', 8),
            # Major mismatch -> ignored (this is the validation fix):
            ('1.0-1.el8_10', '9', None),
            ('611.5.1.el9_7', '8', None),
            # No minor in the dist tag - cannot determine:
            ('1.0-1.el9', '9', None),
            ('1.0-1', '9', None),
            ('', '9', None),
            (None, '9', None),
        ],
    )
    def test_parse(self, release, target_major, expected):
        assert lib.parse_kernel_minor(release, target_major) == expected


class TestParseReleaseMinor:
    """Extract the minor from a cloudlinux-release RPM version field,
    requiring the major to match the target.
    """

    @pytest.mark.parametrize(
        ('version', 'target_major', 'expected'),
        [
            ('9.6', '9', 6),
            ('9.7', '9', 7),
            ('8.10', '8', 10),
            ('9.6.1', '9', 6),
            # Major mismatch -> ignored (this is the validation fix):
            ('8.10', '9', None),
            ('9.6', '8', None),
            # Major-only or junk - cannot determine:
            ('9', '9', None),
            ('', '9', None),
            (None, '9', None),
            ('garbage', '9', None),
        ],
    )
    def test_parse(self, version, target_major, expected):
        assert lib.parse_release_minor(version, target_major) == expected


# ---------------------------------------------------------------------------
# Process: kernel-minor vs release-minor comparison
# ---------------------------------------------------------------------------


def _make_query(kernel_rows, release_rows):
    """Inject canned repoquery results for kernel-core and cloudlinux-release."""

    def query(installroot, pkg):
        if pkg == 'kernel-core':
            return kernel_rows
        if pkg == 'cloudlinux-release':
            return release_rows
        return []

    return query


@pytest.fixture
def captured_reports(monkeypatch):
    """Collect every reporting.create_report() call made by the library."""
    sink = []
    monkeypatch.setattr(lib.reporting, 'create_report', lambda parts: sink.append(parts))
    return sink


def _report_groups(report_parts):
    """Return the list of group strings from a captured create_report() call."""
    for part in report_parts:
        # leapp's reporting.Groups carries `fields={'groups': [...]}` via its
        # ``__init__``.  Walk attributes that look like the groups list.
        groups = getattr(part, 'value', None)
        if isinstance(groups, list) and groups and all(isinstance(g, str) for g in groups):
            return groups
    return []


class TestProcess:
    def test_match_no_inhibit(self, captured_reports):
        """Newest kernel minor equals newest release minor -> upgrade proceeds."""
        q = _make_query(
            kernel_rows=[('5.14.0', '570.12.1.el9_6'), ('5.14.0', '570.62.1.el9_6')],
            release_rows=[('9.6', '7.el9')],
        )
        lib.process(installroot='/var/lib/leapp/el9userspace', query_fn=q, target_major='9')
        assert captured_reports == []

    def test_kernel_minor_ahead_inhibits(self, captured_reports):
        """CLOS-3716: kernel el9_7 available while cloudlinux-release still at 9.6."""
        q = _make_query(
            kernel_rows=[('5.14.0', '570.12.1.el9_6'), ('5.14.0', '611.5.1.el9_7')],
            release_rows=[('9.6', '7.el9')],
        )
        lib.process(installroot='/var/lib/leapp/el9userspace', query_fn=q, target_major='9')
        assert len(captured_reports) == 1
        groups = _report_groups(captured_reports[0])
        assert 'inhibitor' in groups
        assert 'kernel' in groups

    def test_release_ahead_no_inhibit(self, captured_reports):
        """Release minor ahead of kernel minor - not the rollout-leak shape."""
        q = _make_query(
            kernel_rows=[('5.14.0', '570.12.1.el9_6')],
            release_rows=[('9.6', '7.el9'), ('9.7', '1.el9')],
        )
        lib.process(installroot='/var/lib/leapp/el9userspace', query_fn=q, target_major='9')
        assert captured_reports == []

    def test_missing_kernel_data_no_inhibit(self, captured_reports):
        """Empty repoquery for kernel-core -> no determination, no report."""
        q = _make_query(kernel_rows=[], release_rows=[('9.6', '7.el9')])
        lib.process(installroot='/var/lib/leapp/el9userspace', query_fn=q, target_major='9')
        assert captured_reports == []

    def test_missing_release_data_no_inhibit(self, captured_reports):
        """Empty repoquery for cloudlinux-release -> no determination, no report."""
        q = _make_query(kernel_rows=[('5.14.0', '570.12.1.el9_6')], release_rows=[])
        lib.process(installroot='/var/lib/leapp/el9userspace', query_fn=q, target_major='9')
        assert captured_reports == []

    def test_el8_10_path(self, captured_reports):
        """el8_10 must parse as minor 10 (>= 9) so el7->el8 path works too."""
        q = _make_query(
            kernel_rows=[('4.18.0', '513.5.1.el8_9'), ('4.18.0', '600.1.1.el8_10')],
            release_rows=[('8.9', '1.el8')],
        )
        lib.process(installroot='/var/lib/leapp/el8userspace', query_fn=q, target_major='8')
        assert len(captured_reports) == 1

    def test_cross_major_packages_ignored(self, captured_reports):
        """The target userspace's repoquery returns source-major packages too;
        rows for the wrong major must be ignored (validation found this on a
        live VM where `cloudlinux-release-8.10` made the unfiltered code
        report a meaningless `9.10` minor).
        """
        q = _make_query(
            kernel_rows=[
                # Target el9 entries:
                ('5.14.0', '570.12.1.el9_6'),
                # Source el8 entries that must NOT be counted (no minor tag here, but
                # an el8_N row must also not bleed into the el9 max):
                ('4.18.0', '348.lve.el8'),
                ('4.18.0', '600.1.1.el8_10'),
            ],
            release_rows=[
                ('8.10', '1.el8'), ('8.10', '7.el8'),  # source-major - ignore
                ('9.6', '7.el9'),                     # only this counts for target=9
            ],
        )
        lib.process(installroot='/var/lib/leapp/el9userspace', query_fn=q, target_major='9')
        assert captured_reports == []  # kernel minor 6 == release minor 6


def test_skips_targets_without_minor_versions(monkeypatch):
    """CloudLinux 10 has no minor versions, so there is no minor skew to check.

    cloudlinux-release on CL10 is version "10", not "10.2", so the release-minor
    parser returns None and the check already does nothing - but by accident,
    which reads like a bug to the next person. Skip explicitly, and do not even
    query the repositories.
    """
    queried = []

    def recording_query(installroot, pkg):
        queried.append(pkg)
        return []

    monkeypatch.setattr(lib.api, 'current_logger', logger_mocked())
    lib.process('/installroot', query_fn=recording_query, target_major='10')

    assert queried == []
    assert any('no minor versions' in msg for msg in lib.api.current_logger.infomsg)


def test_still_checks_targets_that_do_have_minors(monkeypatch):
    """The skip must be specific to majors without minors, not a blanket off switch."""
    queried = []

    def recording_query(installroot, pkg):
        queried.append(pkg)
        return []

    monkeypatch.setattr(lib.api, 'current_logger', logger_mocked())
    lib.process('/installroot', query_fn=recording_query, target_major='9')

    assert queried == ['kernel-core', 'cloudlinux-release']


def test_repoquery_tolerates_an_unavailable_repo(monkeypatch):
    """One broken repository must not silently switch this check off.

    The query runs against the target userspace, which inherits the source
    system's repofiles. A stale one - cl-mysql, whose baseurl interpolates
    $releasever and 404s on the target - makes dnf exit 1 for every query. This
    library then reads two empty lists, logs "could not determine both minors"
    and returns, so the CLOS-3716 guard is off on exactly the kind of untidy box
    most likely to need it.
    """
    seen = {}

    def fake_run(cmd, **dummy):
        seen['cmd'] = cmd
        return {'stdout': '5.14.0|611.5.1.el9_7\n'}

    monkeypatch.setattr(lib, "run", fake_run)
    monkeypatch.setattr(lib.api, "current_logger", logger_mocked())
    monkeypatch.setattr(lib.api, "current_actor", CurrentActorMocked(dst_ver="9.8"))

    rows = lib._repoquery("/installroot", "kernel-core")

    assert rows == [('5.14.0', '611.5.1.el9_7')]
    assert any('skip_if_unavailable=1' in arg for arg in seen['cmd'])


def test_repoquery_reads_the_channel_the_transaction_will(monkeypatch):
    """cloudlinux-release comes from cloudlinux-x86_64-server-$releasever, and
    without --releasever dnf reads the bare-major channel instead of the target
    minor's - so the check compared the kernel against a channel the upgrade
    never installs from."""
    seen = {}

    def fake_run(cmd, **dummy):
        seen['cmd'] = cmd
        return {'stdout': ''}

    monkeypatch.setattr(lib, "run", fake_run)
    monkeypatch.setattr(lib.api, "current_logger", logger_mocked())
    monkeypatch.setattr(lib.api, "current_actor", CurrentActorMocked(dst_ver="9.8"))

    lib._repoquery("/installroot", "cloudlinux-release")

    assert '--releasever=9.8' in seen['cmd']
