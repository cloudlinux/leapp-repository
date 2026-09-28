import collections
import os
import re
from enum import Enum

from leapp.libraries.common.config.version import get_source_major_version, get_target_major_version
from leapp.libraries.stdlib import CalledProcessError, api, run
from leapp.models import (
    PESIDRepositoryEntry,
    RepoMapEntry,
    RepositoriesMapping,
)


class ClMysqlTypeStatus(Enum):
    OK = "ok"
    MISMATCH = "mismatch"


ClMysqlTypeResult = collections.namedtuple(
    "ClMysqlTypeResult", ["status", "governor_type", "pkg_type"]
)

# MySQL Governor tracks the DB type in two files:
#   mysql.type           - the *desired* type set by --mysql-version (may be ahead of reality)
#   mysql.type.installed - the *actually installed* type, written after a successful --install
# For Leapp we need what is really on disk, so we read mysql.type.installed.
# Both files are present on CL7 and CL8+ when governor-mysql is installed.
GOVERNOR_INSTALLED_TYPE_FILE = "/usr/share/lve/dbgovernor/mysql.type.installed"

# The operating system's own database server packages: the "distro" variant, as
# opposed to the Governor builds (cl-MySQL*, cl-MariaDB*) and the vendors'
# (mysql-community-server, MariaDB-server). Variants are never swapped for each other.
DISTRO_DB_SERVERS = {
    "mysql-server": "MySQL",
    "mariadb-server": "MariaDB",
}

# Matches the version directory Governor puts in the cl-mysql-meta repository URL, e.g.
# ".../mysqlmeta/cl-mariadb-11.04/$basearch/" -> ("mariadb", "11", "04").
CLMYSQL_REPO_URL_RE = re.compile(r"cl-(mariadb|mysql|percona)-(\d+)\.(\d+)", re.IGNORECASE)

# Capitalisation Governor uses for the DNF module stream of each family.
CLMYSQL_FAMILY_CAMEL = {"mariadb": "MariaDB", "mysql": "MySQL", "percona": "Percona"}

# This dict matches the MySQL type strings with DNF module and stream IDs.
MODULE_STREAMS = {
    "mysql55": "mysql:cl-MySQL55",
    "mysql56": "mysql:cl-MySQL56",
    "mysql57": "mysql:cl-MySQL57",
    "mysql80": "mysql:cl-MySQL80",
    "mysql84": "mysql:cl-MySQL84",
    "mariadb55": "mariadb:cl-MariaDB55",
    "mariadb100": "mariadb:cl-MariaDB100",
    "mariadb101": "mariadb:cl-MariaDB101",
    "mariadb102": "mariadb:cl-MariaDB102",
    "mariadb103": "mariadb:cl-MariaDB103",
    "mariadb104": "mariadb:cl-MariaDB104",
    "mariadb105": "mariadb:cl-MariaDB105",
    "mariadb106": "mariadb:cl-MariaDB106",
    "mariadb1011": "mariadb:cl-MariaDB1011",
    "mariadb1104": "mariadb:cl-MariaDB1104",
    # No mariadb1108 entry on purpose. Governor declares mariadb:cl-MariaDB1108, but the
    # published cl-mariadb-11.08 repository carries no modules.yaml on cl8 or cl9 (unlike
    # cl-mariadb-11.04), so that stream cannot be confirmed to exist. Leaving it out keeps
    # the "module stream was derived automatically" warning, which is the signal we want
    # until the 11.08 content question is settled.
    "percona56": "percona:cl-Percona56",
}


def parse_clmysql_type(clmysql_type):
    """
    Return ``(family, major, minor)`` for a Governor DB type token, or None.

    Governor spells the token by concatenating the major and minor version, and the
    spelling is not consistent across series: MariaDB 11.4 is ``mariadb1104`` (minor
    padded to two digits) while 10.6 is ``mariadb106`` (not padded).  Governor also
    re-derives the token from the RPM version when it caches it in mysql.type.installed
    (``mysql_version()`` in install/utilities.py), which drops that padding again and
    yields ``mariadb114`` for the very same installation.

    Comparing the numeric triple instead of the spelling makes the two forms equal -
    ``mariadb114`` and ``mariadb1104`` both parse to ``("mariadb", 11, 4)`` - so no
    table of Governor's spellings has to be kept in sync here (CLOS-6809).

    :param clmysql_type: type string such as ``mariadb114``, ``mariadb1104``, ``mysql80``
    :returns: ``(family, major, minor)``, or None when the token is not recognised
    """
    match = re.match(r"^(mariadb|mysql|percona)(\d+)$", clmysql_type or "")
    if not match:
        return None

    family, digits = match.group(1), match.group(2)
    # Two-digit tokens are a one-digit major ("mysql57" -> 5.7); longer ones are a
    # two-digit major ("mariadb106" -> 10.6, "mariadb1104" -> 11.04).
    split = 1 if len(digits) <= 2 else 2
    return family, int(digits[:split]), int(digits[split:])


def parse_clmysql_repo_url(baseurl):
    """
    Return ``(family, major, minor)`` for a cl-mysql-meta baseurl, or None.

    Parsing the version out of the URL and comparing it numerically avoids having to
    predict how Governor spelled the directory: ``cl-mariadb-11.04`` and a hypothetical
    ``cl-mariadb-11.4`` both parse to ``("mariadb", 11, 4)``.
    """
    match = CLMYSQL_REPO_URL_RE.search(baseurl or "")
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2)), int(match.group(3))


def canonical_clmysql_type(clmysql_type):
    """
    Return the spelling of *clmysql_type* that MODULE_STREAMS knows, if there is one.

    Only the DNF module lookup still needs Governor's exact spelling, because the stream
    name is built from it (``mariadb1104`` -> ``cl-MariaDB1104``).  MODULE_STREAMS is the
    registry of streams we have confirmed, so try the token as given and then with the
    minor version padded back to two digits, and use whichever it lists.

    Unknown tokens are returned unchanged; the caller then derives a stream name and
    reports that it did so, which is the existing signal for a series nobody has
    verified yet.
    """
    if not clmysql_type or clmysql_type in MODULE_STREAMS:
        return clmysql_type

    parsed = parse_clmysql_type(clmysql_type)
    if not parsed:
        return clmysql_type

    family, major, minor = parsed
    candidate = "{}{}{:02d}".format(family, major, minor)
    if candidate in MODULE_STREAMS:
        api.current_logger().debug(
            "CL-MySQL type '{}' matches known module stream entry '{}'".format(clmysql_type, candidate)
        )
        return candidate

    return clmysql_type


def clmysql_module_stream_from_url(baseurl):
    """
    Derive (dnf_module_name, stream) from the cl-mysql-meta repository directory.

    The directory carries the same digits as the module stream, padding included -
    cl-mariadb-11.04 goes with cl-MariaDB1104, cl-mariadb-10.6 with cl-MariaDB106 -
    so the stream can be read off the repository the system is actually configured for
    instead of being guessed from the cached type token, which has lost that padding.
    That guess produced cl-MariaDB114 for MariaDB 11.4, and would produce
    cl-MariaDB124 for a future 12.4, neither of which exists.

    Only meaningful once the repository has been confirmed to describe the installed
    database: clmysql_process() inhibits the upgrade before reaching this point when
    the two disagree.

    :returns: ``(module_name, stream)`` or ``(None, None)`` if the URL is not recognised
    """
    match = CLMYSQL_REPO_URL_RE.search(baseurl or "")
    if not match:
        return None, None
    family = match.group(1).lower()
    # group(2)/group(3) are the raw digits, so "11.04" stays "1104" and not "114".
    return family, "cl-{}{}{}".format(CLMYSQL_FAMILY_CAMEL[family], match.group(2), match.group(3))


def resolve_clmysql_module_stream(clmysql_type, baseurl=None):
    """
    Return (dnf_module_name, stream) for CloudLinux Governor MySQL/MariaDB/Percona types.

    Prefer MODULE_STREAMS, which lists the streams we have confirmed exist.  Otherwise
    read the stream off the configured cl-mysql-meta repository, which spells the
    version the same way the stream does.  Only when no repository is available does
    this fall back to deriving from the type token, which cannot recover a minor
    version whose leading zero Governor dropped.

    :param clmysql_type: Governor DB type token, e.g. ``mariadb1104`` or ``mariadb114``
    :param baseurl: cl-mysql-meta baseurl, when one has been matched to the installed DB
    """
    if not clmysql_type:
        return None, None

    clmysql_type = canonical_clmysql_type(clmysql_type)

    entry = MODULE_STREAMS.get(clmysql_type)
    if entry:
        mod_name, mod_stream = entry.split(":", 1)
        return mod_name, mod_stream

    mod_name, mod_stream = clmysql_module_stream_from_url(baseurl)
    if mod_name and mod_stream:
        api.current_logger().debug(
            "Derived DNF module {}:{} for CL-MySQL type '{}' from the configured repository."
            .format(mod_name, mod_stream, clmysql_type)
        )
        return mod_name, mod_stream

    match = re.match(r"^(mariadb)(\d+)$", clmysql_type)
    if match:
        return "mariadb", "cl-MariaDB{}".format(match.group(2))

    match = re.match(r"^(mysql)(\d+)$", clmysql_type)
    if match:
        return "mysql", "cl-MySQL{}".format(match.group(2))

    match = re.match(r"^(percona)(\d+)$", clmysql_type)
    if match:
        return "percona", "cl-Percona{}".format(match.group(2))

    return None, None


def _resolve_mysqld_path():
    """
    Return absolute path to mysqld: ``which`` first, then usual daemon locations.

    Uses a subprocess call instead of :func:`shutil.which` so the code works on
    Python 2.7 (EL7) where ``shutil.which`` does not exist.
    """
    try:
        result = run(["which", "mysqld"])
        path = result["stdout"].strip()
        if path:
            return path
    except (CalledProcessError, OSError):
        pass
    for candidate in ("/usr/sbin/mysqld", "/usr/libexec/mysqld", "/usr/bin/mysqld"):
        if os.path.isfile(candidate):
            return candidate
    return None


def _clmysql_name_version_from_rpm(path):
    """
    Query the RPM that owns ``path`` and return (name_lower, version_lower) for the first
    CloudLinux cl-{mariadb,mysql,percona} package when several packages claim the file.
    """
    try:
        rpm_out = run(
            [
                "rpm",
                "-qf",
                path,
                "--queryformat",
                "%{NAME} %{VERSION}\\n",
            ]
        )["stdout"]
    except CalledProcessError as err:
        api.current_logger().info(
            "Could not query RPM owner of mysqld path {0}: {1}".format(path, str(err))
        )
        return None

    for line in rpm_out.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            api.current_logger().info(
                "Unexpected rpm --queryformat line for {0!r}: {1!r}".format(path, line)
            )
            continue
        name, version = parts[0].lower(), parts[1].lower()
        if "cl-mariadb" in name or "cl-mysql" in name or "cl-percona" in name:
            return name, version

    return None


def get_clmysql_version_from_pkg():
    """
    Detect the current installed CL-MySQL/MariaDB/Percona version from the mysqld binary.
    """
    mysqld_path = _resolve_mysqld_path()
    if not mysqld_path:
        api.current_logger().info(
            "CL-MySQL version detection failed: mysqld not found in PATH or standard locations"
        )
        return None

    pair = _clmysql_name_version_from_rpm(mysqld_path)
    if not pair:
        api.current_logger().info(
            "CL-MySQL version detection failed: no CloudLinux cl-mysql/cl-mariadb/cl-percona "
            "package owns {0}".format(mysqld_path)
        )
        return None

    name, version = pair
    if "cl-mariadb" in name:
        name = "mariadb"
    elif "cl-mysql" in name:
        name = "mysql"
    elif "cl-percona" in name:
        name = "percona"
    else:
        return None

    # The same concatenation Governor uses, so this agrees with mysql.type.installed
    # by construction. It is lossy ("11.4.12" -> "mariadb114"), which is why callers
    # compare parse_clmysql_type() triples rather than these strings.
    return "%s%s" % (name, "".join(version.split(".")[:2]))


def get_pkg_prefix(clmysql_type):
    """
    Get a Yum package prefix string from cl-mysql type.
    """
    if clmysql_type.startswith("mysql"):
        return "cl-MySQL"
    elif clmysql_type.startswith("mariadb"):
        return "cl-MariaDB"
    elif clmysql_type.startswith("percona"):
        return "cl-Percona"
    else:
        return None


def _get_clmysql_type_from_governor():
    """
    Read the actually installed DB type from the MySQL Governor cache file.

    Governor stores the desired type in `mysql.type` (written by `--mysql-version`)
    and the actually installed type in `mysql.type.installed` (written after a
    successful `--install`).  We read the installed file so that a pending
    `--mysql-version` that was never followed by `--install` does not mislead Leapp.

    The cached value is not necessarily the token the administrator passed to
    `--mysql-version`: Governor re-derives it from the mysqld owner RPM
    (`mysql_version()` in install/utilities.py), which loses a leading zero in the
    minor version, so a MariaDB 11.4 system caches `mariadb114` rather than
    `mariadb1104`.  Both spellings are returned as-is; callers compare
    parse_clmysql_type() triples, which treats them as the same version (CLOS-6809).

    Returns a type string like `mariadb106`, or None when Governor is absent,
    the file is missing/empty, or the value is `auto`.
    """
    if not os.path.isfile(GOVERNOR_INSTALLED_TYPE_FILE):
        return None
    try:
        with open(GOVERNOR_INSTALLED_TYPE_FILE, "r") as f:
            value = f.read().strip()
    except (IOError, OSError) as err:
        api.current_logger().warning(
            "Could not read Governor mysql.type.installed file: {}".format(err)
        )
        return None
    if not value or value == "auto":
        return None
    return value


def get_clmysql_type():
    """
    Get the currently active CL MySQL/MariaDB/Percona type.

    Prefer the MySQL Governor config file (authoritative when Governor manages the DB),
    fall back to detecting the type from the mysqld binary's RPM ownership.

    When both sources are available, cross-check them. On mismatch, return a
    result with :attr:`ClMysqlTypeStatus.MISMATCH` so the caller can raise an inhibitor.

    The two sources are compared as parsed versions rather than as strings: Governor may
    have cached ``mariadb114`` for the same installation whose canonical token is
    ``mariadb1104``, and treating that spelling difference as a mismatch inhibited the
    upgrade on every MariaDB 11.x system (CLOS-6809).

    :returns: :class:`ClMysqlTypeResult` with status, resolved type, and raw detection values.
    """
    governor_type = _get_clmysql_type_from_governor()
    pkg_type = get_clmysql_version_from_pkg()

    # Fall back to comparing the raw strings when either side is unparseable, so two
    # different unrecognised values are still reported rather than both becoming None.
    governor_version = parse_clmysql_type(governor_type)
    pkg_version = parse_clmysql_type(pkg_type)
    if governor_version and pkg_version:
        differ = governor_version != pkg_version
    else:
        differ = governor_type != pkg_type

    if governor_type and pkg_type and differ:
        api.current_logger().warning(
            "Governor mysql.type.installed says '{}' but RPM-based detection says '{}'."
            .format(governor_type, pkg_type)
        )
        return ClMysqlTypeResult(
            status=ClMysqlTypeStatus.MISMATCH,
            governor_type=governor_type,
            pkg_type=pkg_type,
        )

    if governor_type:
        api.current_logger().debug(
            "CL-MySQL type from Governor file: {}".format(governor_type)
        )

    return ClMysqlTypeResult(
        status=ClMysqlTypeStatus.OK,
        governor_type=governor_type,
        pkg_type=pkg_type,
    )


# ---------------------------------------------------------------------------
# Repository mapping helpers
# ---------------------------------------------------------------------------

def make_pesid_repo(pesid, major_version, repoid, arch='x86_64', repo_type='rpm', channel='ga', rhui='',
                    distro='cloudlinux'):
    """
    PESIDRepositoryEntry factory function allowing shorter data description by providing default values.

    ``distro`` became a required field of PESIDRepositoryEntry with repomap format
    1.3.0. RepoMapDataHandler matches entries against get_source_distro_id(), which
    is the /etc/os-release ID - 'cloudlinux' on every host this library runs on.
    """
    return PESIDRepositoryEntry(
        pesid=pesid,
        major_version=major_version,
        repoid=repoid,
        arch=arch,
        repo_type=repo_type,
        channel=channel,
        rhui=rhui,
        distro=distro
    )


def construct_repomap_data(source_id, target_id):
    """
    Construct the repository mapping data.
    """
    source_major = get_source_major_version()
    target_major = get_target_major_version()
    return RepositoriesMapping(
        mapping=[RepoMapEntry(source=source_id, target=[target_id])],
        repositories=[
            make_pesid_repo(source_id, source_major, source_id),
            make_pesid_repo(target_id, target_major, target_id)
        ]
    )
