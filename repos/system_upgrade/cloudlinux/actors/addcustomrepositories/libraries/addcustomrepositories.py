import os
import os.path
import shutil
import logging

from leapp.libraries.stdlib import api
from leapp.libraries.common import cl_repofileutils

CUSTOM_REPOS_FOLDER = 'custom-repos'


def add_custom(log):
    # type: (logging.Logger) -> None
    custom_repo_dir = api.get_common_folder_path(CUSTOM_REPOS_FOLDER)
    repofiles = os.listdir(custom_repo_dir)

    # If any components are missing, halt.
    if not repofiles or not custom_repo_dir:
        return

    # Write into the directory dnf actually reads (honors a non-default
    # reposdir such as /etc/yum.repos.local.d).
    repo_root_path = cl_repofileutils.get_primary_repo_dir()

    for repofile in repofiles:
        full_repo_path = os.path.join(custom_repo_dir, repofile)

        log.debug("Copying repo file {} to {}".format(repofile, repo_root_path))

        shutil.copy(full_repo_path, repo_root_path)
