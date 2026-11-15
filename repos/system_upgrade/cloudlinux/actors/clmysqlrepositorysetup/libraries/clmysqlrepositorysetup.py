"""
Coordinator for MySQL/MariaDB repository setup during CloudLinux ELevate upgrades.

Delegates repo-specific logic to handler modules:
  - clmysql_cloudlinux:       Governor-managed CL MySQL/MariaDB/Percona
  - clmysql_upstream_mariadb: upstream mariadb.org repositories
  - clmysql_upstream_mysql:   upstream mysql.com repositories
"""
import os

from leapp import reporting
from leapp.libraries.common import repofileutils
from leapp.libraries.common.cl_repofileutils import (
    LEAPP_COPY_SUFFIX,
    REPO_DIR,
    REPOFILE_SUFFIX,
)
from leapp.libraries.common.clmysql import (
    DISTRO_DB_SERVERS,
    MODULE_STREAMS,
    canonical_clmysql_type,
    clmysql_module_stream_from_url,
    construct_repomap_data,
    get_pkg_prefix,
    resolve_clmysql_module_stream,
    target_has_module_streams,
)
from leapp.libraries.common.rpms import has_package
from leapp.libraries.stdlib import api
from leapp.models import (
    InstalledMySqlTypes,
    InstalledRPM,
    Module,
    RpmTransactionTasks,
)

from leapp.libraries.actor.clmysql_cloudlinux import clmysql_process
from leapp.libraries.actor.clmysql_upstream_mariadb import mariadb_process
from leapp.libraries.actor.clmysql_upstream_mysql import mysql_process

CL_MARKERS = ["cl-mysql", "cl-mariadb", "cl-percona"]
MARIA_MARKERS = ["MariaDB"]
MYSQL_MARKERS = ["mysql-community"]


def build_install_list(prefix):
    """
    Find the installed cl-mysql packages that match the active
    cl-mysql type as per Governor config.

    :param prefix: Package name prefix to search for.
    :return: List of matching packages.
    """
    to_upgrade = []
    if prefix:
        for rpm_pkgs in api.consume(InstalledRPM):
            for pkg in rpm_pkgs.items:
                if pkg.name.startswith(prefix):
                    to_upgrade.append(pkg.name)
        api.current_logger().debug("cl-mysql packages to upgrade: {}".format(to_upgrade))
    return to_upgrade


class MySqlRepositorySetupLibrary(object):
    """
    Detect the various MySQL/MariaDB variants that may be installed on the system
    and prepare the repositories for the target system.
    Not all configurations can be handled by normal static Leapp configurations,
    so we need custom code to handle them.
    """

    def __init__(self):
        self.mysql_types = set()
        self.clmysql_type = None
        # baseurl of the cl-mysql-meta repo, once confirmed to match the installed DB.
        self.clmysql_meta_baseurl = None
        # Messages to send about custom generated package repositories.
        self.custom_repo_msgs = []
        self.mapping_msgs = []

    def finalize(self):
        """Use the data collected to produce messages and reports."""
        if len(self.mysql_types) == 0:
            api.current_logger().debug("No installed MySQL/MariaDB detected")
        else:
            reporting.create_report(
                [
                    reporting.Title("MySQL database backup recommended"),
                    reporting.Summary(
                        "A MySQL/MariaDB installation has been detected on this machine. "
                        "It is recommended to make a database backup before proceeding with the upgrade."
                    ),
                    reporting.Severity(reporting.Severity.HIGH),
                    reporting.Groups([reporting.Groups.REPOSITORY]),
                ]
            )

            for msg in self.custom_repo_msgs:
                api.produce(msg)
            for msg in self.mapping_msgs:
                api.produce(msg)

            if len(self.mysql_types) == 1:
                api.current_logger().debug(
                    "Detected MySQL/MariaDB type: {}, version: {}".format(list(self.mysql_types)[0], self.clmysql_type)
                )
            else:
                api.current_logger().warning("Detected multiple MySQL types: {}".format(", ".join(self.mysql_types)))
                reporting.create_report(
                    [
                        reporting.Title("Multpile MySQL/MariaDB versions detected"),
                        reporting.Summary(
                            "Package repositories for multiple distributions of MySQL/MariaDB "
                            "were detected on the system. "
                            "Leapp will attempt to update all distributions detected. "
                            "To update only the distribution you use, disable YUM package repositories for all "
                            "other distributions. "
                            "Detected: {0}".format(", ".join(self.mysql_types))
                        ),
                        reporting.Severity(reporting.Severity.MEDIUM),
                        reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.OS_FACTS]),
                    ]
                )

        if "cloudlinux" in self.mysql_types and self.clmysql_type and not target_has_module_streams():
            # No stream to enable on the target, so the packages are upgraded as plain
            # packages. Requesting one did nothing but log it as unavailable.
            api.produce(RpmTransactionTasks(to_upgrade=build_install_list(get_pkg_prefix(self.clmysql_type))))
        elif "cloudlinux" in self.mysql_types and self.clmysql_type:
            mod_name, mod_stream = resolve_clmysql_module_stream(
                self.clmysql_type, baseurl=self.clmysql_meta_baseurl
            )
            if mod_name and mod_stream:
                # Ask where the stream actually came from. Governor caches a spelling that
                # MODULE_STREAMS does not list ("mariadb114" for MariaDB 11.4), so testing
                # the raw token would report a verified stream as though it had been guessed.
                if canonical_clmysql_type(self.clmysql_type) in MODULE_STREAMS:
                    stream_source = None
                elif clmysql_module_stream_from_url(self.clmysql_meta_baseurl)[1] == mod_stream:
                    stream_source = "the configured cl-mysql repository"
                else:
                    stream_source = "the detected database type"

                if stream_source:
                    api.current_logger().warning(
                        "CL database type {} is not in MODULE_STREAMS; using DNF module {}:{} derived "
                        "from {}. Add an explicit MODULE_STREAMS entry when this stream is "
                        "product-supported."
                        .format(self.clmysql_type, mod_name, mod_stream, stream_source)
                    )
                    reporting.create_report(
                        [
                            reporting.Title("CloudLinux database module stream was derived automatically"),
                            reporting.Summary(
                                "The active CloudLinux MySQL/MariaDB/Percona type ({0}) has no explicit Leapp "
                                "MODULE_STREAMS entry. Leapp will enable DNF module {1}:{2}, derived from "
                                "{3}. If the upgrade fails, confirm this module exists for the target OS and "
                                "add MODULE_STREAMS in Leapp if the product stream name differs."
                                .format(self.clmysql_type, mod_name, mod_stream, stream_source)
                            ),
                            reporting.Severity(reporting.Severity.MEDIUM),
                            reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.OS_FACTS]),
                        ]
                    )

                api.current_logger().debug("Enabling DNF module: {}:{}".format(mod_name, mod_stream))
                pkg_prefix = get_pkg_prefix(self.clmysql_type)
                modules_to_enable = [Module(name=mod_name, stream=mod_stream)]
                api.produce(
                    RpmTransactionTasks(to_upgrade=build_install_list(pkg_prefix), modules_to_enable=modules_to_enable)
                )
            else:
                api.current_logger().warning(
                    "CL DB package type {} could not be mapped to a DNF module stream; "
                    "skipping modules_to_enable for CloudLinux DB packages."
                    .format(self.clmysql_type)
                )
                reporting.create_report(
                    [
                        reporting.Title("Unrecognized CloudLinux DB type for module enablement"),
                        reporting.Summary(
                            "A CloudLinux-provided DB repository was detected, but the active type "
                            "({0}) does not match known MODULE_STREAMS and could not be converted to a DNF module "
                            "name/stream. Leapp will not enable a DB module automatically; the upgrade "
                            "may fail unless repositories and modules are corrected manually."
                            .format(self.clmysql_type)
                        ),
                        reporting.Severity(reporting.Severity.HIGH),
                        reporting.Groups([reporting.Groups.REPOSITORY, reporting.Groups.OS_FACTS]),
                    ]
                )

        api.produce(
            InstalledMySqlTypes(
                types=list(self.mysql_types),
                version=self.clmysql_type,
            )
        )

    def process(self):
        """Main processing function."""

        for repofile_full in os.listdir(REPO_DIR):
            # Don't touch non-repository files or copied repofiles created by Leapp.
            if repofile_full.endswith(LEAPP_COPY_SUFFIX) or not repofile_full.endswith(REPOFILE_SUFFIX):
                continue
            # Cut the .repo part to get only the name.
            repofile_name = repofile_full[: -len(REPOFILE_SUFFIX)]
            full_repo_path = os.path.join(REPO_DIR, repofile_full)
            repofile_data = repofileutils.parse_repofile(full_repo_path)

            # Parse any CL repository files that may have something to do with MySQL or MariaDB.
            if any(mark in repofile_name for mark in CL_MARKERS):
                api.current_logger().debug(
                    "Processing CL-related repofile {}, full path: {}".format(repofile_full, full_repo_path)
                )
                clmysql_process(self, repofile_name, repofile_data)

            # Process MariaDB options.
            elif any(mark in repofile_name for mark in MARIA_MARKERS):
                api.current_logger().debug(
                    "Processing MariaDB-related repofile {}, full path: {}".format(repofile_full, full_repo_path)
                )
                mariadb_process(self, repofile_name, repofile_data)

            # Process MySQL options.
            elif any(mark in repofile_name for mark in MYSQL_MARKERS):
                api.current_logger().debug(
                    "Processing MySQL-related repofile {}, full path: {}".format(repofile_full, full_repo_path)
                )
                mysql_process(self, repofile_name, repofile_data)

        # The operating system's own server has no repository file of its own, so it
        # is recognised by package name. Whether it can be carried to the target is
        # decided later, by check_cl_mysql_target, from the settled transaction.
        if any(has_package(InstalledRPM, name) for name in DISTRO_DB_SERVERS):
            self.mysql_types.add("distro")

        self.finalize()
