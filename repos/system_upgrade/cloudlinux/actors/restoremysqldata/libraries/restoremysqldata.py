import os

from leapp import reporting
from leapp.libraries.common import backup
from leapp.libraries.stdlib import api


def process():
    failed_files = []

    for filepath in backup.CLSQL_BACKUP_FILES:
        name = os.path.basename(filepath)
        if not os.path.isfile(os.path.join(backup.BACKUP_DIR, name)):
            # backup_my_sql_data copies only the files the source system had.
            api.current_logger().debug('No backup of {}, nothing to restore'.format(filepath))
            continue
        try:
            backup.restore_file(name, filepath)
        except OSError as e:
            failed_files.append(filepath)
            api.current_logger().error('Could not restore file {}: {}'.format(filepath, e.strerror))

    if failed_files:
        title = "Failed to restore backed up configuration files"
        summary = (
            "Some backed up configuration files were unable to be restored automatically."
            " Please check the upgrade log for detailed error descriptions"
            " and restore the files from the backup directory {} manually if needed."
            " Files not restored: {}".format(backup.BACKUP_DIR, failed_files)
        )
        reporting.create_report(
            [
                reporting.Title(title),
                reporting.Summary(summary),
                reporting.Severity(reporting.Severity.HIGH),
                reporting.Groups([reporting.Groups.UPGRADE_PROCESS]),
            ]
        )
