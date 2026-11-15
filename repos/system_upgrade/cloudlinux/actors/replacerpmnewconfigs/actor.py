from __future__ import print_function
import os
import fileinput

from leapp.actors import Actor
from leapp.tags import ApplicationsPhaseTag, IPUWorkflowTag
from leapp import reporting
from leapp.reporting import Report
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.backup import backup_and_remove, LEAPP_BACKUP_SUFFIX
from leapp.libraries.common import cl_repofileutils

# These markers are used to identify which repository files should be directly replaced with new versions.
REPO_DELETE_MARKERS = ['cloudlinux', 'imunify']
# These markers are used to identify which repository files should be replaced with new versions and backed up.
REPO_BACKUP_MARKERS = []
# This suffix is used to identify .rpmnew files that appear after package upgrade.
RPMNEW = '.rpmnew'


class ReplaceRpmnewConfigs(Actor):
    """
    Replace CloudLinux-related repository config .rpmnew files.
    """

    name = 'replace_rpmnew_configs'
    consumes = ()
    produces = (Report,)
    tags = (ApplicationsPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
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
                    self.log.debug('Yum repofile replaced: {}'.format(main_file_path))

                if any(mark in rpmnew_filename for mark in REPO_BACKUP_MARKERS) and rpmnew_filename.endswith(RPMNEW):
                    main_reponame = rpmnew_filename[:-len(RPMNEW)]
                    main_file_path = os.path.join(repo_dir, main_reponame)
                    rpmnew_file_path = os.path.join(repo_dir, rpmnew_filename)

                    backup_and_remove(main_file_path)
                    os.rename(rpmnew_file_path, main_file_path)
                    renamed_repofiles.append(main_reponame)
                    self.log.debug('Yum repofile replaced with backup: {}'.format(main_file_path))

            # Disable any old repositories.
            for repofile_name in os.listdir(repo_dir):
                if LEAPP_BACKUP_SUFFIX in repofile_name:
                    repofile_path = os.path.join(repo_dir, repofile_name)
                    for line in fileinput.input(repofile_path, inplace=True):
                        if line.startswith('enabled'):
                            print("enabled = 0")
                        else:
                            print(line, end='')

        if renamed_repofiles or deleted_repofiles:
            deleted_string = '\n'.join(['{}'.format(repofile_name) for repofile_name in deleted_repofiles])
            replaced_string = '\n'.join(['{}'.format(repofile_name) for repofile_name in renamed_repofiles])
            reporting.create_report([
                reporting.Title('Repository config files replaced by updated versions'),
                reporting.Summary(
                    'One or more RPM repository configuration files '
                    'have been replaced with new versions provided by the upgraded packages. '
                    'Any manual modifications to these files have been overriden by this process. '
                    'Old versions of backed up files are contained in files with a naming pattern '
                    '<repository_file_name>.leapp-backup. '
                    'Deleted repository files: \n{}\n'
                    'Backed up repository files: \n{}'.format(deleted_string, replaced_string)
                ),
                reporting.Severity(reporting.Severity.MEDIUM),
                reporting.Groups([reporting.Groups.UPGRADE_PROCESS])
            ])
