import shutil
import tempfile

from leapp import reporting
from leapp.libraries.stdlib import api, CalledProcessError, run
from leapp.models import LiveModeConfig

# The command system_upgrade/common's mount_unit_generator runs during 'leapp
# upgrade', where any failure aborts the upgrade. Kept in step with it by
# test_upstream_still_runs_the_generator_this_check_mirrors.
GENERATOR = '/usr/lib/systemd/system-generators/systemd-fstab-generator'


def _generator_messages(error):
    text = '\n'.join(part for part in (error.stderr, error.stdout) if part)
    return [line.strip() for line in text.splitlines() if line.strip()]


def process():
    livemode = next(api.consume(LiveModeConfig), None)
    if livemode and livemode.is_enabled:
        # mount_unit_generator does not run the generator in LiveMode either.
        return

    scratch = tempfile.mkdtemp(prefix='leapp-fstab-check-')
    try:
        run([GENERATOR, scratch, scratch, scratch])
    except CalledProcessError as error:
        messages = _generator_messages(error) or [str(error)]
        reporting.create_report([
            reporting.Title('systemd cannot generate mount units from /etc/fstab'),
            reporting.Summary(
                'The upgrade runs systemd-fstab-generator to prepare the mounts of the'
                ' upgrade environment, and stops there if it fails - after the upgrade has'
                ' started. It fails on this system:\n\n    {0}\n\nA duplicated line in'
                ' /etc/fstab is enough: systemd tolerates it at boot, but the generator'
                ' does not.'.format('\n    '.join(messages))
            ),
            reporting.Severity(reporting.Severity.HIGH),
            reporting.Groups([reporting.Groups.FILESYSTEM, reporting.Groups.INHIBITOR]),
            reporting.Remediation(
                hint='Fix the /etc/fstab entries named above - for a duplicate, remove the'
                     ' extra line - then check with "{0} /tmp/x /tmp/x /tmp/x" and run the'
                     ' upgrade again.'.format(GENERATOR)
            ),
            reporting.RelatedResource('file', '/etc/fstab'),
        ])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
