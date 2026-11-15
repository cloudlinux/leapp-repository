import os
import os.path

from leapp.libraries.stdlib import api
from leapp.libraries.common import repofileutils

ROLLOUT_MARKER = 'rollout'
CL_MARKERS = ['cloudlinux', 'imunify']

REPO_DIR = '/etc/yum.repos.d'
TEMP_DIR = '/var/lib/leapp/yum_custom_repofiles'
LEAPP_COPY_SUFFIX = "_leapp_custom.repo"
REPOFILE_SUFFIX = ".repo"


def get_repo_dirs():
    """
    Return the list of directories dnf actually scans for .repo files.

    Honors a non-default ``reposdir`` (e.g. a host that relocates its repos
    to /etc/yum.repos.local.d), so CloudLinux actors must not assume the standard
    /etc/yum.repos.d. Falls back to the standard location if dnf cannot
    report the configured directories (e.g. the dnf module is unavailable).
    """
    try:
        repo_dirs = repofileutils.get_repodirs()
    except Exception as e:  # dnf missing / main-config read failure
        api.current_logger().warning(
            'Could not determine reposdir from dnf ({}); falling back to {}'.format(e, REPO_DIR)
        )
        repo_dirs = []
    return repo_dirs or [REPO_DIR]


def get_primary_repo_dir():
    """
    Return the directory new .repo files should be written to so that dnf
    will read them: the first configured reposdir (the default when unset).
    """
    return get_repo_dirs()[0]


def is_rollout_repository(repofile):
    return ROLLOUT_MARKER in repofile and any(mark in repofile for mark in CL_MARKERS)


def create_leapp_repofile_copy(repofile_data, repo_name):
    """
    Create a copy of an existing Yum repository config file, modified
    to be used during the Leapp transaction.
    It will be placed inside the isolated overlay environment Leapp runs the upgrade from.

    :param repofile_data: Data of the repository file copy to be created.
    :type repofile_data: RepositoryFile
    :param repo_name: Name of the rollout repository file, without the .repo extension.
    :type repo_name: str
    :return: Path to the created copy of the repository file.
    :rtype: str
    """
    if not os.path.isdir(TEMP_DIR):
        os.makedirs(TEMP_DIR)
    leapp_repofile = repo_name + LEAPP_COPY_SUFFIX
    leapp_repo_path = os.path.join(TEMP_DIR, leapp_repofile)
    if os.path.exists(leapp_repo_path):
        os.unlink(leapp_repo_path)

    api.current_logger().debug('Producing a Leapp repofile copy: {}'.format(leapp_repo_path))
    repofileutils.save_repofile(repofile_data, leapp_repo_path)
    return leapp_repo_path
