"""
Handler for upstream (mariadb.org) MariaDB repositories.
"""
import copy
import re

from leapp import reporting
from leapp.libraries.common.cl_repofileutils import create_leapp_repofile_copy
from leapp.libraries.common.clmysql import construct_repomap_data
from leapp.libraries.common.config.version import get_source_major_version, get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import (
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RepositoryFile,
)

# MariaDB series that upstream never published for el9, so a CL8 -> CL9 upgrade has
# nothing to move their packages to. Verified 2026-07-30: for both series, el8
# exists but el9 is a 404 on rpm.mariadb.org *and* on archive.mariadb.org, so
# there is no alternative host to fall back to either. Only checked for a CL8
# source: the same rewrite on CL7 -> CL8 yields /rhel/8/, which does exist.
OLD_MARIADB_UPSTREAM_VERSIONS_CL8 = ["10.3", "10.4"]

# Distro names MariaDB uses in its repository paths. The OS major version always
# sits immediately after one of these, either as its own path segment ("/rhel/8/")
# or glued onto the name ("/almalinux8-amd64/").
MARIADB_DISTRO_NAMES = (
    "almalinux",
    "centos",
    "fedora",
    "opensuse",
    "rhel",
    "rockylinux",
    "rocky",
    "sles",
)

_DISTRO_VERSION_RE = re.compile(
    r"/(?P<distro>{distros})(?P<sep>/?)(?P<version>\$releasever|\d+)(?=[/-]|$)".format(
        distros="|".join(MARIADB_DISTRO_NAMES)
    )
)

# Used to keep the rewrite off the scheme and host, so that a host such as
# "rhel8-mirror.example.com" cannot be mistaken for a distro directory.
_URL_HOST_RE = re.compile(r"^(?P<head>[a-zA-Z][a-zA-Z0-9+.-]*://[^/]*)(?P<path>/.*)$")


def _make_upgrade_mariadb_url(mariadb_url, source_major, target_major):
    """
    Rewrite an upstream MariaDB repo URL for the target OS version.

    Maria URLs look like this::

        baseurl = https://archive.mariadb.org/mariadb-10.3/yum/centos/7/x86_64
        baseurl = https://archive.mariadb.org/mariadb-10.7/yum/centos7-ppc64/
        baseurl = https://distrohub.kyiv.ua/mariadb/yum/11.8/rhel/$releasever/$basearch
        baseurl = https://mariadb.gb.ssimn.org/yum/12.0/centos/$releasever/$basearch
        baseurl = https://mariadb.gb.ssimn.org/yum/12.0/almalinux8-amd64/
        baseurl = https://rpm.mariadb.org/10.6/rhel/$releasever/$basearch

    The OS major version is always the token right after the distro name, so we
    anchor on the distro name and rewrite just that token. This used to anchor on
    a literal "yum" path segment instead, which missed the last form entirely:
    rpm.mariadb.org is the dynamic mirror that mariadb.org's own repo-config
    generator recommends when a chosen mirror goes offline, and its paths have no
    "yum" segment. Anchoring on the distro name also keeps the MariaDB version in
    the path safe - "/10.7/rhel/7/" must only have the second 7 rewritten.

    $releasever is replaced outright because upstream repos only have major
    version directories, while CloudLinux expands $releasever to major.minor.

    :return: the rewritten URL, or None if the URL was not understood.
    """
    if not mariadb_url:
        api.current_logger().warning("Unsupported repository URL={}, skipping".format(mariadb_url))
        return None

    host_match = _URL_HOST_RE.match(mariadb_url)
    head, path = (host_match.group("head"), host_match.group("path")) if host_match else ("", mariadb_url)

    matches = list(_DISTRO_VERSION_RE.finditer(path))
    if not matches:
        api.current_logger().warning("Unsupported repository URL={}, skipping".format(mariadb_url))
        return None

    def _rewrite(match):
        # Only touch the version we expect to find, so that an unrelated number
        # sitting after a distro name cannot be mangled.
        if match.group("version") not in ("$releasever", str(source_major)):
            return match.group(0)
        return "/{}{}{}".format(match.group("distro"), match.group("sep"), target_major)

    new_path = _DISTRO_VERSION_RE.sub(_rewrite, path)
    if new_path == path and not any(m.group("version") == str(target_major) for m in matches):
        # Nothing was rewritten, and the URL does not already point at the target
        # OS version either - so we did not understand it after all.
        api.current_logger().warning("Unsupported repository URL={}, skipping".format(mariadb_url))
        return None
    return head + new_path


def mariadb_process(lib, repofile_name, repofile_data):
    """
    Process upstream MariaDB options.

    Versions of MariaDB installed from https://mariadb.org/.

    :param lib: :class:`MySqlRepositorySetupLibrary` instance (shared state).
    :param repofile_name: repository file name without ``.repo`` suffix.
    :param repofile_data: parsed :class:`RepositoryFile`.
    """

    cl_target_repofile_list = []
    target_major = get_target_major_version()
    source_major = get_source_major_version()

    for source_repo in repofile_data.data:
        if not source_repo.enabled:
            continue

        target_repo = copy.deepcopy(source_repo)
        target_repo.repoid = "{}-{}".format(target_repo.repoid, target_major)
        target_repo.baseurl = _make_upgrade_mariadb_url(source_repo.baseurl, source_major, target_major)

        if not target_repo.baseurl:
            # Stop here instead of generating the repository anyway. A
            # CustomTargetRepository with no baseurl is written into the target
            # repofile as the literal string "baseurl = None", and the target
            # transaction then dies with "Cannot find a valid baseurl for repo:
            # <repoid>" - an error that says nothing about the actual cause. The
            # URL warning logged above was easy to miss for the same reason.
            reporting.create_report(
                [
                    reporting.Title("Cannot map an upstream MariaDB repository to the target system"),
                    reporting.Summary(
                        "The enabled MariaDB repository '{0}' uses a base URL that Leapp does not know how "
                        "to rewrite for the target system: {1}. Without it, no MariaDB repository would be "
                        "available during the upgrade and the installed MariaDB packages could not be "
                        "upgraded, so the upgrade is blocked. The target repository would have been "
                        "'{2}'.".format(source_repo.repoid, source_repo.baseurl, target_repo.repoid)
                    ),
                    reporting.Severity(reporting.Severity.HIGH),
                    reporting.Groups([reporting.Groups.REPOSITORY]),
                    reporting.Groups([reporting.Groups.INHIBITOR]),
                    reporting.Remediation(
                        hint=(
                            "Change the repository base URL to one that points at the distro and OS major "
                            "version explicitly (for example https://rpm.mariadb.org/10.6/rhel/8/$basearch), "
                            "or uninstall the MariaDB packages and disable the repository before upgrading."
                        )
                    ),
                ]
            )
            continue

        # This MariaDB series has no packages built for the target OS at all.
        if str(source_major) == "8" and any(
            ver in target_repo.baseurl for ver in OLD_MARIADB_UPSTREAM_VERSIONS_CL8
        ):
            reporting.create_report(
                [
                    reporting.Title("Upstream MariaDB has no packages for the target system"),
                    reporting.Summary(
                        "The enabled upstream MariaDB repository is for a MariaDB series that was "
                        "never published for the target system, so rewriting its base URL points at "
                        "a repository that does not exist. The installed MariaDB packages would have "
                        "no upgrade candidate and would be left behind at their current versions, "
                        "which is why the upgrade is blocked. Leapp cannot resolve this "
                        "automatically. Repository: {0}, base URL that would have been used: "
                        "{1}".format(target_repo.repoid, target_repo.baseurl)
                    ),
                    reporting.Severity(reporting.Severity.MEDIUM),
                    reporting.Groups([reporting.Groups.REPOSITORY]),
                    reporting.Groups([reporting.Groups.INHIBITOR]),
                    reporting.Remediation(
                        hint=(
                            "Move MariaDB to a version that upstream builds for the target system "
                            "(see https://mariadb.org/download/) before upgrading, or uninstall the "
                            "MariaDB packages and disable the repository. Note that you will also "
                            "need to update any bindings (e.g., PHP or Python) that are dependent on "
                            "this MariaDB version."
                        )
                    ),
                ]
            )

        api.current_logger().debug("Generating custom MariaDB repo: {}".format(target_repo.repoid))
        lib.custom_repo_msgs.append(
            CustomTargetRepository(
                repoid=target_repo.repoid,
                name=target_repo.name,
                baseurl=target_repo.baseurl,
                enabled=target_repo.enabled,
            )
        )
        lib.mapping_msgs.append(
            construct_repomap_data(source_repo.repoid, target_repo.repoid)
        )
        cl_target_repofile_list.append(target_repo)

    if any(repo.enabled for repo in repofile_data.data):
        lib.mysql_types.add("mariadb")

    if cl_target_repofile_list:
        # Since MariaDB URLs have major versions written in, we need a new repo file
        # to feed to the target userspace.
        cl_target_repofile_data = RepositoryFile(data=cl_target_repofile_list, file=repofile_data.file)
        leapp_repocopy = create_leapp_repofile_copy(cl_target_repofile_data, repofile_name)
        api.produce(CustomTargetRepositoryFile(file=leapp_repocopy))
    else:
        api.current_logger().debug(
            "No usable target repos generated from MariaDB repofile {}, ignoring".format(repofile_name)
        )
