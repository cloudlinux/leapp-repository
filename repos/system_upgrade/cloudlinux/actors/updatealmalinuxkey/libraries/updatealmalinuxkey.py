"""Import the target distribution's GPG keys before the download phase."""

import os

from leapp import reporting
from leapp.libraries.common.gpg import get_path_to_gpg_certs
from leapp.libraries.stdlib import api, CalledProcessError, run


def _iter_shipped_keys():
    """Yield the paths of every GPG key shipped for the target major version."""
    for certs_dir in get_path_to_gpg_certs():
        if not os.path.isdir(certs_dir):
            # /etc/leapp/files/vendors.d/rpm-gpg/ is only there when a vendor
            # ships keys, so an absent directory is the normal case.
            continue
        for name in sorted(os.listdir(certs_dir)):
            path = os.path.join(certs_dir, name)
            if os.path.isfile(path):
                yield path


def _report_failure(title, summary):
    reporting.create_report([
        reporting.Title(title),
        reporting.Summary(summary),
        reporting.Remediation(
            hint='Check that leapp-data for this upgrade path is installed and intact,'
                 ' then run the upgrade again.'
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([reporting.Groups.OS_FACTS]),
        reporting.Groups([reporting.Groups.INHIBITOR]),
    ])


def process():
    imported = 0
    for key_path in _iter_shipped_keys():
        try:
            res = run(['rpm', '--import', key_path])
            api.current_logger().debug('Imported GPG key %s: %s', key_path, res)
            imported += 1
        except CalledProcessError as err:
            _report_failure(
                'Failed to import the target distribution GPG key.',
                'Importing {0} failed with exit code {1}. Packages signed with that key'
                ' cannot be verified, so the upgrade transaction would fail partway'
                ' through.'.format(key_path, err.exit_code)
            )
            return
        except OSError as err:
            api.current_logger().error(
                'Could not call an RPM command: Message: %s', str(err), exc_info=True
            )
            return

    if not imported:
        _report_failure(
            'No target distribution GPG keys were found.',
            'leapp ships the GPG keys for the target major version under {0}, and none'
            ' were found there. Nothing would verify the target packages, and the'
            ' failure would surface later as an unverifiable signature rather than as'
            ' a missing key.'.format(', '.join(get_path_to_gpg_certs()))
        )
