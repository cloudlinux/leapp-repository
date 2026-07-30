import pytest

from leapp.libraries.actor.clmysql_upstream_mariadb import _make_upgrade_mariadb_url, mariadb_process


@pytest.mark.parametrize(
    "source_url,source_major,target_major,expected_url",
    [
        # Test cases from docstring
        (
            "https://archive.mariadb.org/mariadb-10.3/yum/centos/7/x86_64",
            7, 8,
            "https://archive.mariadb.org/mariadb-10.3/yum/centos/8/x86_64",
        ),
        (
            "https://archive.mariadb.org/mariadb-10.7/yum/centos7-ppc64/",
            7, 8,
            "https://archive.mariadb.org/mariadb-10.7/yum/centos8-ppc64/",
        ),
        (
            "https://distrohub.kyiv.ua/mariadb/yum/11.8/rhel/7/x86_64",
            7, 8,
            "https://distrohub.kyiv.ua/mariadb/yum/11.8/rhel/8/x86_64",
        ),
        (
            "https://mariadb.gb.ssimn.org/yum/12.0/centos/7/x86_64",
            7, 8,
            "https://mariadb.gb.ssimn.org/yum/12.0/centos/8/x86_64",
        ),
        (
            "https://mariadb.gb.ssimn.org/yum/12.0/almalinux8-amd64/",
            8, 9,
            "https://mariadb.gb.ssimn.org/yum/12.0/almalinux9-amd64/",
        ),

        # Test with trailing slash
        (
            "https://archive.mariadb.org/mariadb-10.3/yum/centos/7/x86_64/",
            7, 8,
            "https://archive.mariadb.org/mariadb-10.3/yum/centos/8/x86_64/",
        ),

         # Test cases based on SSIMN.org mirror patterns
         # RHEL patterns
         (
             "https://mariadb.gb.ssimn.org/yum/12.0/rhel8-amd64/",
             8, 9,
             "https://mariadb.gb.ssimn.org/yum/12.0/rhel9-amd64/",
         ),

         # Rocky Linux patterns
         (
             "https://mariadb.gb.ssimn.org/yum/12.0/rocky8-amd64/",
             8, 9,
             "https://mariadb.gb.ssimn.org/yum/12.0/rocky9-amd64/",
         ),
         (
             "https://mariadb.gb.ssimn.org/yum/12.0/rockylinux8-amd64/",
             8, 9,
             "https://mariadb.gb.ssimn.org/yum/12.0/rockylinux9-amd64/",
         ),

        # Canonical mariadb.org "dynamic mirror" layout. These have no /yum/
        # path segment, which the original implementation used as its anchor,
        # so they used to come back as None. The repo config generator at
        # https://mariadb.org/download/ ships this host as the documented
        # fallback ("rpm.mariadb.org is a dynamic mirror if your preferred
        # mirror goes offline"), so real systems do run it.
        (
            "https://rpm.mariadb.org/10.6/rhel/7/x86_64",
            7, 8,
            "https://rpm.mariadb.org/10.6/rhel/8/x86_64",
        ),
        (
            "https://rpm.mariadb.org/10.6/rhel/$releasever/$basearch",
            7, 8,
            "https://rpm.mariadb.org/10.6/rhel/8/$basearch",
        ),
        (
            "https://rpm.mariadb.org/12.0/centos/$releasever/$basearch",
            8, 9,
            "https://rpm.mariadb.org/12.0/centos/9/$basearch",
        ),
        (
            "https://rpm.mariadb.org/11.4/almalinux8-amd64/",
            8, 9,
            "https://rpm.mariadb.org/11.4/almalinux9-amd64/",
        ),
        # The MariaDB version in the path must survive the rewrite even when it
        # ends in the source major version.
        (
            "https://rpm.mariadb.org/10.7/rhel/7/x86_64",
            7, 8,
            "https://rpm.mariadb.org/10.7/rhel/8/x86_64",
        ),
        (
            "https://dlm.mariadb.com/repo/mariadb-server/11/rhel/8/$basearch",
            8, 9,
            "https://dlm.mariadb.com/repo/mariadb-server/11/rhel/9/$basearch",
        ),

        # Deliberate behaviour change: this used to be expected to return None,
        # purely because the path has no "yum" segment. That expectation was
        # pinning the old anchor, and the anchor is what broke rpm.mariadb.org.
        # A mirror laid out as <distro>/<major> is mappable no matter what the
        # rest of the path looks like, so it is now mapped.
        (
            "https://example.com/mariadb/repo/centos/7/x86_64",
            7, 8,
            "https://example.com/mariadb/repo/centos/8/x86_64",
        ),

        # Test cases that should return None and log warning
        (
            "https://example.com/mariadb/yum",
            7, 8,
            None,
        ),
        # No distro/version anywhere to anchor on - still unmappable.
        (
            "https://example.com/mariadb/repo/x86_64",
            7, 8,
            None,
        ),
        # The host must be left alone: "rhel8-mirror" is not a distro directory.
        (
            "https://rhel8-mirror.example.com/mariadb/11.4/rhel/8/$basearch",
            8, 9,
            "https://rhel8-mirror.example.com/mariadb/11.4/rhel/9/$basearch",
        ),
        # A version that is neither $releasever nor the source major version is
        # left alone, so there is nothing to rewrite.
        (
            "https://rpm.mariadb.org/10.6/rhel/6/x86_64",
            7, 8,
            None,
        ),
        (
            "",
            7, 8,
            None,
        ),
        (
            None,
            7, 8,
            None,
        ),
    ]
)
def test_make_upgrade_mariadb_url(source_url, source_major, target_major, expected_url):
    """Test URL transformation for various MariaDB repository URLs."""
    result = _make_upgrade_mariadb_url(source_url, source_major, target_major)

    assert result == expected_url


class _LibStub(object):
    """Minimal stand-in for MySqlRepositorySetupLibrary."""

    def __init__(self):
        self.mysql_types = set()
        self.custom_repo_msgs = []
        self.mapping_msgs = []


@pytest.fixture
def patch_mariadb_env(monkeypatch):
    """
    Patch clmysql_upstream_mariadb's dependencies, in the same style as patch_env
    in conftest.py. Defaults to a CL7 -> CL8 upgrade. Returns (api, reporting) so
    tests can assert against the leapp mocks.
    """
    from leapp import reporting
    from leapp.libraries.common.testutils import (
        create_report_mocked,
        logger_mocked,
        produce_mocked,
    )
    from leapp.libraries.stdlib import api

    def _apply(source_major="7", target_major="8"):
        monkeypatch.setattr(
            "leapp.libraries.actor.clmysql_upstream_mariadb.get_source_major_version",
            lambda: source_major,
        )
        monkeypatch.setattr(
            "leapp.libraries.actor.clmysql_upstream_mariadb.get_target_major_version",
            lambda: target_major,
        )
        # construct_repomap_data() resolves the versions again through its own
        # imports, straight out of the actor configuration, so it has to be
        # patched at that site too - otherwise the call reaches
        # api.current_actor() and dies outside a real leapp run.
        monkeypatch.setattr(
            "leapp.libraries.common.clmysql.get_source_major_version", lambda: source_major)
        monkeypatch.setattr(
            "leapp.libraries.common.clmysql.get_target_major_version", lambda: target_major)
        monkeypatch.setattr(
            "leapp.libraries.actor.clmysql_upstream_mariadb.create_leapp_repofile_copy",
            lambda repofile_data, repo_name: "/tmp/{}_leapp_custom.repo".format(repo_name),
        )
        monkeypatch.setattr(api, "produce", produce_mocked())
        monkeypatch.setattr(api, "current_logger", logger_mocked())
        monkeypatch.setattr(reporting, "create_report", create_report_mocked())
        return api, reporting

    return _apply


def _mariadb_repofile(baseurl, enabled=True):
    from leapp.models import RepositoryData, RepositoryFile

    return RepositoryFile(
        file="/etc/yum.repos.d/MariaDB.repo",
        data=[RepositoryData(repoid="mariadb", name="MariaDB", baseurl=baseurl, enabled=enabled)],
    )


@pytest.mark.parametrize("source_major,target_major", [("7", "8"), ("8", "9")])
def test_mariadb_process_never_emits_a_repo_without_a_baseurl(
        patch_mariadb_env, source_major, target_major):
    """
    An unmappable source URL must stop the repository being generated at all.

    Regression test for the failure seen on CL7->CL8 in elevate-qa: the URL was
    rejected by _make_upgrade_mariadb_url (which logged "Unsupported repository
    URL=..., skipping") and the repository was then generated anyway with
    baseurl=None. repofileutils.save_repofile() wrote the literal string
    "baseurl = None" into the target repofile, and the target transaction died
    with the unactionable "Error: Cannot find a valid baseurl for repo:
    mariadb-8".

    The 8->9 parameter additionally covers a latent crash: the CL8 MariaDB
    version guard did `any(ver in target_repo.baseurl ...)`, which raises
    TypeError when baseurl is None.
    """
    api, reporting = patch_mariadb_env(source_major=source_major, target_major=target_major)
    lib = _LibStub()

    mariadb_process(lib, "MariaDB", _mariadb_repofile("https://example.com/mariadb/yum"))

    assert lib.custom_repo_msgs == []
    assert lib.mapping_msgs == []
    assert api.produce.called == 0

    # ...and the admin is told why, instead of being left with the dnf error.
    assert reporting.create_report.called == 1
    summary = reporting.create_report.reports[0]["summary"]
    assert "mariadb-{}".format(target_major) in summary
    assert "https://example.com/mariadb/yum" in summary
    assert "inhibitor" in reporting.create_report.reports[0]["groups"]


def test_mariadb_process_generates_repo_for_mariadb_org_dynamic_mirror(patch_mariadb_env):
    """The rpm.mariadb.org layout must produce a usable target repo."""
    api, reporting = patch_mariadb_env()
    lib = _LibStub()

    mariadb_process(lib, "MariaDB", _mariadb_repofile("https://rpm.mariadb.org/10.6/rhel/7/$basearch"))

    assert len(lib.custom_repo_msgs) == 1
    repo = lib.custom_repo_msgs[0]
    assert repo.repoid == "mariadb-8"
    assert repo.baseurl == "https://rpm.mariadb.org/10.6/rhel/8/$basearch"
    assert lib.mysql_types == set(["mariadb"])
    assert reporting.create_report.called == 0
    assert [msg.file for msg in api.produce.model_instances] == ["/tmp/MariaDB_leapp_custom.repo"]


@pytest.mark.parametrize("series", ["10.3", "10.4"])
def test_mariadb_process_inhibits_series_with_no_target_packages(patch_mariadb_env, series):
    """
    CL8 -> CL9 must be inhibited for MariaDB series upstream never built for el9.

    Verified 2026-07-30: for 10.3 and 10.4 the el8 repository exists but el9 is a
    404 on rpm.mariadb.org *and* on archive.mariadb.org, so the rewritten base URL
    points at nothing and the installed packages would have no upgrade candidate.

    This path had no test coverage at all, which is how the report came to explain
    the symptom ("not compatible with Leapp upgrade") rather than the cause.
    """
    api, reporting = patch_mariadb_env(source_major="8", target_major="9")
    lib = _LibStub()

    mariadb_process(
        lib, "MariaDB",
        _mariadb_repofile("https://rpm.mariadb.org/{0}/rhel/8/$basearch".format(series)))

    assert reporting.create_report.called == 1
    report = reporting.create_report.reports[0]
    assert "inhibitor" in report["groups"]
    # The report must name the repo and the URL it would have used, so the admin
    # can see *why* rather than just being told "not compatible".
    assert "mariadb-9" in report["summary"]
    assert "https://rpm.mariadb.org/{0}/rhel/9/$basearch".format(series) in report["summary"]

    # Existing behaviour, asserted so a later change to it is deliberate: the repo
    # is still generated. The inhibitor is what stops the upgrade, not the absence
    # of the repository.
    assert [r.repoid for r in lib.custom_repo_msgs] == ["mariadb-9"]


def test_mariadb_process_allows_series_that_upstream_still_builds(patch_mariadb_env):
    """A series with el9 packages must not trip the no-target-packages inhibitor."""
    api, reporting = patch_mariadb_env(source_major="8", target_major="9")
    lib = _LibStub()

    mariadb_process(
        lib, "MariaDB", _mariadb_repofile("https://rpm.mariadb.org/11.4/rhel/8/$basearch"))

    assert reporting.create_report.called == 0
    assert lib.custom_repo_msgs[0].baseurl == "https://rpm.mariadb.org/11.4/rhel/9/$basearch"


def test_mariadb_process_ignores_disabled_repos(patch_mariadb_env):
    """A disabled source repo is neither mapped nor reported on."""
    api, reporting = patch_mariadb_env()
    lib = _LibStub()

    mariadb_process(
        lib, "MariaDB", _mariadb_repofile("https://example.com/mariadb/yum", enabled=False))

    assert lib.custom_repo_msgs == []
    assert reporting.create_report.called == 0
    assert api.produce.called == 0
