from __future__ import print_function
import os
import fileinput

from leapp.libraries.stdlib import api
from leapp.libraries.common.backup import backup_and_remove, LEAPP_BACKUP_SUFFIX
from leapp.libraries.common import cl_repofileutils

# These markers are used to identify which repository files should be directly replaced with new versions.
REPO_DELETE_MARKERS = ['cloudlinux', 'imunify']
# These markers are used to identify which repository files should be replaced with new versions and backed up.
REPO_BACKUP_MARKERS = []
# This suffix is used to identify .rpmnew files that appear after package upgrade.
RPMNEW = '.rpmnew'


def replace_rpmnew_configs():
    """
    Apply CloudLinux-related repofile .rpmnew files in every directory dnf reads.

    :return: names of the repofiles replaced outright, and of those replaced
             after being backed up
    :rtype: tuple(list(str), list(str))
    """
    deleted_repofiles = []
    renamed_repofiles = []

    for repo_dir in cl_repofileutils.get_repo_dirs():
        if not os.path.isdir(repo_dir):
            continue

        for rpmnew_filename in os.listdir(repo_dir):
            if any(mark in rpmnew_filename for mark in REPO_DELETE_MARKERS) and rpmnew_filename.endswith(RPMNEW):
                main_reponame = rpmnew_filename[:-len(RPMNEW)]
                main_file_path = os.path.join(repo_dir, main_reponame)
                rpmnew_file_path = os.path.join(repo_dir, rpmnew_filename)

                os.unlink(main_file_path)
                os.rename(rpmnew_file_path, main_file_path)
                deleted_repofiles.append(main_reponame)
                api.current_logger().debug('Yum repofile replaced: {}'.format(main_file_path))

            if any(mark in rpmnew_filename for mark in REPO_BACKUP_MARKERS) and rpmnew_filename.endswith(RPMNEW):
                main_reponame = rpmnew_filename[:-len(RPMNEW)]
                main_file_path = os.path.join(repo_dir, main_reponame)
                rpmnew_file_path = os.path.join(repo_dir, rpmnew_filename)

                backup_and_remove(main_file_path)
                os.rename(rpmnew_file_path, main_file_path)
                renamed_repofiles.append(main_reponame)
                api.current_logger().debug('Yum repofile replaced with backup: {}'.format(main_file_path))

        # Disable any old repositories.
        for repofile_name in os.listdir(repo_dir):
            if LEAPP_BACKUP_SUFFIX in repofile_name:
                repofile_path = os.path.join(repo_dir, repofile_name)
                for line in fileinput.input(repofile_path, inplace=True):
                    if line.startswith('enabled'):
                        print("enabled = 0")
                    else:
                        print(line, end='')

    return deleted_repofiles, renamed_repofiles
