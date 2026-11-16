from leapp.actors import Actor
from leapp.tags import ApplicationsPhaseTag, IPUWorkflowTag
from leapp import reporting
from leapp.reporting import Report
from leapp.libraries.actor import replacerpmnewconfigs
from leapp.libraries.common.cllaunch import run_on_cloudlinux


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
        deleted_repofiles, renamed_repofiles = replacerpmnewconfigs.replace_rpmnew_configs()

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
