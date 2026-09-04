import os

from leapp.libraries.stdlib import api, CalledProcessError, run

CAGEFSCTL = '/usr/sbin/cagefsctl'


def _reinstall_hooks():
    """
    Reinstall the CageFS hooks, which the upgrade transaction could not.

    CageFS installs its hooks from its own %posttrans scriptlet, and does it in
    two steps: the CageFS control panel plugin runs first and, on Plesk,
    deliberately strips the pam_lve.so and pam_sulve.so lines from
    /etc/pam.d/su, then the 'cagefsctl --hook-install' that follows is what puts
    the pam_lve.so line back. Inside the upgrade transaction cagefsctl cannot
    run at all - the system is not booted with systemd as PID 1 and the process
    cannot look itself up in /proc, so cagefsctl fails on startup while setting
    up its logging - which leaves only the stripping half of that pair in
    effect. CageFS users then stop entering the cage through 'su', and cldiag
    reports the pam_lve configuration as missing from /etc/pam.d/su.

    The first boot is a fully booted system, where cagefsctl works, so running
    the same command here installs what the package intended. It is idempotent:
    where the hooks are intact it rewrites the very same configuration.
    """
    try:
        run([CAGEFSCTL, '--hook-install'], checked=True)
        api.current_logger().info('cagefs hooks were reinstalled successfully')
    except CalledProcessError as e:
        # cagefsctl prints errors in stdout
        api.current_logger().error(e.stdout)
        api.current_logger().error(
            'Command "cagefsctl --hook-install" finished with exit code {}, '
            'cagefs users may not enter the cage through "su".\n'
            'Check cagefsctl output above, '
            'rerun "cagefsctl --hook-install" after fixing the issues.'.format(e.exit_code)
        )


def _force_update():
    try:
        run([CAGEFSCTL, '--force-update'], checked=True)
        api.current_logger().info('cagefs update was successful')
    except CalledProcessError as e:
        # cagefsctl prints errors in stdout
        api.current_logger().error(e.stdout)
        api.current_logger().error(
            'Command "cagefsctl --force-update" finished with exit code {}, '
            'the filesystem inside cagefs may be out-of-date.\n'
            'Check cagefsctl output above and in /var/log/cagefs-update.log, '
            'rerun "cagefsctl --force-update" after fixing the issues.'.format(e.exit_code)
        )


def process():
    if not os.path.exists(CAGEFSCTL):
        return

    # The hooks first: the cage rebuild copies /etc from the host system, so the
    # cages get the corrected /etc/pam.d files rather than the stripped ones.
    _reinstall_hooks()
    _force_update()
