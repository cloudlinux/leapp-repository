import os

from leapp import reporting
from leapp.libraries.stdlib import api
from leapp.models import RepositoriesFacts


def get_cldeploy_repo_files(repo_file_paths):
    """
    Get the list of cldeploy repository files.

    Keep in mind that the incoming repository file paths are absolute paths to the repository files.

    cldeploy repofiles are named ``repo.cloudlinux.com_*``; we match on the
    basename rather than a fixed ``/etc/yum.repos.d/`` prefix so this works
    regardless of the directory the file lives in. A system may relocate its
    repositories via ``reposdir`` (e.g. /etc/yum.repos.local.d),
    and RepositoriesFacts already reports the real paths.
    """
    # Name prefix for cldeploy repo files
    repo_prefix = "repo.cloudlinux.com_"

    return [repo_file for repo_file in repo_file_paths
            if os.path.basename(repo_file).startswith(repo_prefix)]


def create_report(cldeploy_repo_files):
    title = "Leftover cldeploy repository files found"
    summary = (
        "The following leftover cldeploy repository files were found on the system. "
        "If not removed, they will cause issues with the upgrade process."
    )

    for repo_file in cldeploy_repo_files:
        summary += "\n- {}".format(repo_file)

    remediation = "Remove the leftover cldeploy repository files before running Leapp again."
    reporting.create_report(
        [
            reporting.Title(title),
            reporting.Summary(summary),
            reporting.Severity(reporting.Severity.HIGH),
            reporting.Groups([reporting.Groups.OS_FACTS, reporting.Groups.REPOSITORY]),
            reporting.Groups([reporting.Groups.INHIBITOR]),
            reporting.Remediation(hint=remediation),
            reporting.RelatedResource('directory', '/etc/yum.repos.d')
        ]
    )


def process():
    repository_file_paths = []
    # RepositoriesFacts.repositories is a list of RepositoryFile objects
    for repos_facts in api.consume(RepositoriesFacts):
        # The file field of RepositoryFile objects is an absolute path to the repository file
        for repo_file in repos_facts.repositories:
            repository_file_paths.append(repo_file.file)

    cldeploy_repo_files = get_cldeploy_repo_files(repository_file_paths)

    if cldeploy_repo_files:
        create_report(cldeploy_repo_files)
