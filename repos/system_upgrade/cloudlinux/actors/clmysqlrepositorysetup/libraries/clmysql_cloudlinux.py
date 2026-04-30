"""
Handler for CloudLinux Governor-managed MySQL/MariaDB/Percona repositories.
"""
import copy

from leapp import reporting
from leapp.libraries.common.cl_repofileutils import create_leapp_repofile_copy
from leapp.libraries.common.clmysql import (
    ClMysqlTypeStatus,
    construct_repomap_data,
    get_clmysql_type,
    get_expected_repo_url_fragment,
)
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import (
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RepositoryFile,
)

OLD_CLMYSQL_VERSIONS = ["5.0", "5.1"]


def clmysql_process(lib, repofile_name, repofile_data):
    """
    Process CL-provided MySQL options.

    :param lib: :class:`MySqlRepositorySetupLibrary` instance (shared state).
    :param repofile_name: repository file name without ``.repo`` suffix.
    :param repofile_data: parsed :class:`RepositoryFile`.
    """
    detected = get_clmysql_type()

    if detected.status == ClMysqlTypeStatus.MISMATCH:
        reporting.create_report(
            [
                reporting.Title(
                    "Mismatch between Governor DB type and installed packages"
                ),
                reporting.Summary(
                    "MySQL Governor records the installed database type as '{governor}', "
                    "but the mysqld binary on disk belongs to '{rpm}'. "
                    "This usually means '/usr/share/lve/dbgovernor/mysqlgovernor.py --mysql-version' was run "
                    "without a follow-up '--install', or packages were changed manually. "
                    "Proceeding could enable the wrong DNF module stream and break the upgrade.".format(
                        governor=detected.governor_type, rpm=detected.pkg_type
                    )
                ),
                reporting.Severity(reporting.Severity.HIGH),
                reporting.Groups(
                    [reporting.Groups.REPOSITORY, reporting.Groups.OS_FACTS]
                ),
                reporting.Groups([reporting.Groups.INHIBITOR]),
                reporting.Remediation(
                    hint=(
                        "Examine the current state of the system's DB packages."
                        "Complete the pending Governor install:\n"
                        "  /usr/share/lve/dbgovernor/mysqlgovernor.py --mysql-version={governor}\n"
                        "  /usr/share/lve/dbgovernor/mysqlgovernor.py --install --yes\n"
                        "Or reset Governor to match the actual packages:\n"
                        "  /usr/share/lve/dbgovernor/mysqlgovernor.py --mysql-version={rpm}\n"
                        "  /usr/share/lve/dbgovernor/mysqlgovernor.py --install --yes\n"
                        "Then restart the upgrade process.".format(
                            governor=detected.governor_type, rpm=detected.pkg_type
                        )
                    )
                ),
            ]
        )
        return

    lib.clmysql_type = detected.governor_type or detected.pkg_type
    if not lib.clmysql_type:
        api.current_logger().warning("CL-MySQL type detection failed, skipping repository mapping")
        return
    api.current_logger().debug("Detected CL-MySQL type: {}".format(lib.clmysql_type))

    data_to_log = [
        (repo_data.repoid, "enabled" if repo_data.enabled else "disabled") for repo_data in repofile_data.data
    ]

    api.current_logger().debug("repoids from CloudLinux repofile {}: {}".format(repofile_name, data_to_log))

    # Validate that cl-mysql-meta repo's baseurl matches the detected DB type.
    # Governor configures the URL based on the selected DB version (e.g. cl-mariadb-10.6 for mariadb106).
    # If the user switched DB versions without re-running Governor --install,
    # the repo may point to the wrong package set.
    # We inhibit rather than auto-correct because Governor is the authoritative source
    # for this repo file and has the real download-and-write logic;
    # re-running --install is the proper fix.
    expected_fragment = get_expected_repo_url_fragment(lib.clmysql_type)
    if expected_fragment:
        for repo_data in repofile_data.data:
            if repo_data.repoid == "cl-mysql-meta" and "/{}/".format(expected_fragment) not in repo_data.baseurl:
                api.current_logger().warning(
                    "cl-mysql-meta repo baseurl '{}' does not match detected DB type '{}' "
                    "(expected '{}' in URL)."
                    .format(repo_data.baseurl, lib.clmysql_type, expected_fragment)
                )
                reporting.create_report(
                    [
                        reporting.Title(
                            "cl-mysql.repo does not match the installed database type"
                        ),
                        reporting.Summary(
                            "The cl-mysql-meta repository is configured for a different "
                            "database type than what is actually installed. "
                            "The detected database type is '{}', but the cl-mysql-meta "
                            "repo URL points to '{}'. "
                            "This may happen when the database version was changed "
                            "without a follow-up '/usr/share/lve/dbgovernor/mysqlgovernor.py --install', or the "
                            "cl-mysql.repo file was manually edited. "
                            "Proceeding with the wrong repository would result in "
                            "an incorrect upgrade operation."
                            .format(lib.clmysql_type, repo_data.baseurl)
                        ),
                        reporting.Severity(reporting.Severity.HIGH),
                        reporting.Groups(
                            [
                                reporting.Groups.REPOSITORY,
                                reporting.Groups.OS_FACTS
                            ]
                        ),
                        reporting.Groups([reporting.Groups.INHIBITOR]),
                        reporting.Remediation(
                            hint=(
                                "Download the correct repository file for the installed "
                                "database type: "
                                "curl -o /etc/yum.repos.d/cl-mysql.repo "
                                "http://repo.cloudlinux.com/other/"
                                "cl${{releasever}}/mysqlmeta/{expected}-common.repo\n"
                                "Or re-run MySQL Governor to regenerate it "
                                "(this reinstalls the full DB stack): "
                                "/usr/share/lve/dbgovernor/mysqlgovernor.py --install --yes\n"
                                "Then restart the upgrade process."
                                .format(expected=expected_fragment)
                            )
                        ),
                    ]
                )
                return

    cl_target_repofile_list = []
    target_major = get_target_major_version()

    for source_repo in repofile_data.data:
        # cl-mysql URLs look like this:
        # baseurl=http://repo.cloudlinux.com/other/cl$releasever/mysqlmeta/cl-mariadb-10.3/$basearch/
        # We don't want any duplicate repoid entries - they'd cause yum/dnf to fail.
        # Make everything unique by adding -<target_major> to the repoid.
        target_repo = copy.deepcopy(source_repo)
        target_repo.repoid = "{}-{}".format(target_repo.repoid, target_major)
        # releasever may be something like 8.6, while only 8 is acceptable.
        target_repo.baseurl = target_repo.baseurl.replace("/cl$releasever/", "/cl{}/".format(target_major))

        # Old CL MySQL versions (5.0 and 5.1) won't be available in CL8+.
        if any(ver in target_repo.baseurl for ver in OLD_CLMYSQL_VERSIONS):
            reporting.create_report(
                [
                    reporting.Title("An old CL-MySQL version will no longer be available in EL{}".format(target_major)),
                    reporting.Summary(
                        "An old CloudLinux-provided MySQL version is installed on this system. "
                        "It will no longer be available on the target system. "
                        "This situation cannot be automatically resolved by Leapp. "
                        "Problematic repository: {0}".format(target_repo.repoid)
                    ),
                    reporting.Severity(reporting.Severity.MEDIUM),
                    reporting.Groups([reporting.Groups.REPOSITORY]),
                    reporting.Groups([reporting.Groups.INHIBITOR]),
                    reporting.Remediation(
                        hint=(
                            "Upgrade to a more recent MySQL version, or "
                            "uninstall the deprecated MySQL packages and disable the repository. "
                            "Note that you will also need to update any bindings (e.g., PHP or Python) "
                            "that are dependent on this MySQL version."
                        )
                    ),
                ]
            )

        # Governor-managed MySQL/MariaDB repos may all be disabled, but we still
        # need them enabled for the target system so DNF can upgrade the packages.
        # Force-enable both cl-mysql-meta and mysqclient target repos.
        if target_repo.enabled or target_repo.repoid in (
            "mysqclient-{}".format(target_major),
            "cl-mysql-meta-{}".format(target_major),
        ):
            api.current_logger().debug("Generating custom cl-mysql repo: {}".format(target_repo.repoid))
            lib.custom_repo_msgs.append(
                CustomTargetRepository(
                    repoid=target_repo.repoid,
                    name=target_repo.name,
                    baseurl=target_repo.baseurl,
                    enabled=True,
                )
            )
            lib.mapping_msgs.append(
                construct_repomap_data(source_repo.repoid, target_repo.repoid)
            )
            # Gather the enabled repositories for the new repofile.
            # They'll be used to create a new custom repofile for the target userspace.
            cl_target_repofile_list.append(target_repo)

    # Always register the cloudlinux type when CL MySQL/MariaDB is detected.
    # Even if all repos in cl-mysql.repo are disabled (can happen with Governor),
    # we still need the target repos for packages like mysqlclient that were
    # installed from local RPMs and have no repo association.
    lib.mysql_types.add("cloudlinux")
    # Provide the object with the modified repository data to the target userspace.
    cl_target_repofile_data = RepositoryFile(data=cl_target_repofile_list, file=repofile_data.file)
    leapp_repocopy = create_leapp_repofile_copy(cl_target_repofile_data, repofile_name)
    api.produce(CustomTargetRepositoryFile(file=leapp_repocopy))
