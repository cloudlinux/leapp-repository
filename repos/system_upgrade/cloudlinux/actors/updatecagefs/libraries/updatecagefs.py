import os

from leapp import reporting
from leapp.libraries.stdlib import api, CalledProcessError, run

CAGEFSCTL = '/usr/sbin/cagefsctl'
PAM_SU_CONFIG = '/etc/pam.d/su'


def _pam_lve_configured():
    """
    Whether /etc/pam.d/su carries a pam_lve session line.

    Same shape as the check cldiag runs through
    clcommon.clconfpars.parse_pam_lve_config(): the first non-comment line
    whose third field is pam_lve.so. Parsed here rather than imported, so that
    a first-boot actor does not depend on the CloudLinux venv being healthy.

    An unreadable config counts as not configured - it cannot be claimed as
    configured on evidence nobody has.
    """
    try:
        with open(PAM_SU_CONFIG) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                fields = line.split()
                if len(fields) >= 3 and fields[2] == 'pam_lve.so':
                    return True
    except (IOError, OSError):
        return False
    return False


def _run_cagefsctl(option):
    """
    Run one cagefsctl subcommand, logging whatever went wrong.

    A cagefsctl that is missing or not executable - the shape of leapp's own
    zero-byte /sbin/new-kernel-pkg stub - raises OSError out of run() rather
    than CalledProcessError. Neither may abort this actor and cost the steps
    that follow.

    :return: True when the command ran and exited zero
    :rtype: bool
    """
    try:
        run([CAGEFSCTL, option], checked=True)
        return True
    except CalledProcessError as e:
        # cagefsctl prints errors in stdout
        api.current_logger().error(e.stdout)
        api.current_logger().error(
            'Command "cagefsctl {}" finished with exit code {}.'.format(option, e.exit_code)
        )
    except OSError as e:
        api.current_logger().error(
            'Command "cagefsctl {}" could not be executed: {}'.format(option, e)
        )
    return False


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

    The exit code cannot be trusted to tell us whether that worked. cagefsctl
    calls HooksInstall() and then exits zero unconditionally, and the pam edit
    inside it swallows IOError and OSError into a printed message - so an
    immutable or read-only /etc/pam.d/su leaves CageFS users uncaged behind a
    clean exit code. Check the resulting configuration instead, and report it,
    because a silent loss of confinement on a successful-looking upgrade is
    not something to leave in a debug log.
    """
    _run_cagefsctl('--hook-install')

    if _pam_lve_configured():
        api.current_logger().info('cagefs hooks were reinstalled successfully')
        return

    api.current_logger().error(
        'The pam_lve configuration is still missing from {} after running '
        '"cagefsctl --hook-install", so cagefs users will not enter the cage '
        'through "su".\n'
        'Check cagefsctl output above, and whether {} is writable, then rerun '
        '"cagefsctl --hook-install".'.format(PAM_SU_CONFIG, PAM_SU_CONFIG)
    )
    reporting.create_report([
        reporting.Title('CageFS users may not enter the cage through "su"'),
        reporting.Summary(
            'The pam_lve configuration is missing from {}, so a CageFS user who'
            ' enters a shell through "su" gets an uncaged one. CageFS installs'
            ' that line from its own %posttrans scriptlet, which cannot run'
            ' inside the upgrade transaction, and reinstalling the hooks on this'
            ' boot did not restore it either. Note that'
            ' "cagefsctl --hook-install" exits zero even when the edit fails, so'
            ' its output may look clean.\n'
            'Restore the configuration by running "cagefsctl --hook-install" and'
            ' confirm it with "cldiag --all" or "cagefsctl --sanity-check".'
            .format(PAM_SU_CONFIG)
        ),
        reporting.Severity(reporting.Severity.HIGH),
        reporting.Groups([reporting.Groups.POST, reporting.Groups.SECURITY]),
    ])


def _force_update():
    if _run_cagefsctl('--force-update'):
        api.current_logger().info('cagefs update was successful')
        return

    api.current_logger().error(
        'The filesystem inside cagefs may be out-of-date.\n'
        'Check cagefsctl output above and in /var/log/cagefs-update.log, '
        'rerun "cagefsctl --force-update" after fixing the issues.'
    )


def process():
    if not os.path.exists(CAGEFSCTL):
        return

    # Scope: CageFS's %posttrans makes 25 cagefsctl calls and this restores two
    # of them. --force-update rebuilds the skeleton and the jails and covers
    # none of the rest - --setup-cl-selector, --update-wrappers,
    # --reconfigure-cagefs, --isolates-regenerate, --sync-proxy-commands and
    # the others are separate option handlers that nothing in the update path
    # reaches. They are lost to the same crash, and the fix for that belongs in
    # clcommon, where it restores all 25 at once: the transaction upgrades the
    # CloudLinux venv and cllib early (around step 1.5k of 7k) and cagefs's
    # %posttrans runs last, so the copy that crashes is the target system's, and
    # a fixed cllib in the target repositories is enough - the source system's
    # does not come into it. Until that ships, this covers the one call whose
    # absence silently stops confining tenants.
    #
    # The hooks first: the cage rebuild copies /etc from the host system, so the
    # cages get the corrected /etc/pam.d files rather than the stripped ones.
    _reinstall_hooks()
    _force_update()
