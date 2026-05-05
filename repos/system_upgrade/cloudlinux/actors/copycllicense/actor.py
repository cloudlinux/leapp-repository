import os
from leapp.actors import Actor
from leapp.reporting import Report
from leapp.tags import ChecksPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.common.cln_detect import is_cln_package_channel_active
from leapp.libraries.stdlib import api
from leapp.models import (
    TargetUserSpacePreupgradeTasks,
    CopyFile
)


RHN_CONFIG_DIR = '/etc/sysconfig/rhn'

# rhn-client-tools is the CLN identity / licensing client. Keep it on the
# target regardless of repo scheme - licensing does not go away under
# no-auth, only repo management does.
LICENSE_PKGS = ['rhn-client-tools']

# dnf-plugin-spacewalk is the DNF plugin that fetches packages from the
# CLN-side spacewalk channel. Pure repo-management plumbing. Under
# no-auth packages come from cl-channel via /etc/yum.repos.d/cl.repo and
# this plugin is unused; rhn-client-tools >= 3.0.1 even Obsoletes it on
# CL8/9.
SPACEWALK_PLUGIN_PKG = 'dnf-plugin-spacewalk'


class CopyClLicense(Actor):
    """
    Produce task to copy CloudLinux license files to target system.
    """

    name = 'copy_rhn_client_tools_config'
    consumes = ()
    produces = (Report, TargetUserSpacePreupgradeTasks)
    tags = (ChecksPhaseTag, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        """
        Produce artifacts to copy RHN configuration files
        and install packages to the target userspace,
        including up2date and systemid.
        """
        files_to_copy = []
        for dirpath, _, filenames in os.walk(RHN_CONFIG_DIR):
            for filename in filenames:
                src_path = os.path.join(dirpath, filename)
                if os.path.isfile(src_path):
                    files_to_copy.append(CopyFile(src=src_path))

        # CLOS-4056: only the spacewalk plugin is repo-management and
        # therefore conditional on the CLN package channel being active.
        # Identity/licensing (rhn-client-tools, /etc/sysconfig/rhn) is
        # unconditional - it stays even when we move the system off CLN as
        # a package source.
        install_rpms = list(LICENSE_PKGS)
        if is_cln_package_channel_active():
            install_rpms.append(SPACEWALK_PLUGIN_PKG)
        else:
            api.current_logger().info(
                "CLN is not the active package channel; skipping %s in target"
                " userspace install set",
                SPACEWALK_PLUGIN_PKG,
            )

        api.produce(TargetUserSpacePreupgradeTasks(
            install_rpms=install_rpms,
            copy_files=files_to_copy
        ))
