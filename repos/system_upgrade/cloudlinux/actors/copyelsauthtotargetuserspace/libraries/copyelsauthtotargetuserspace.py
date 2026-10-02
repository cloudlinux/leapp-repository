"""Carry the CLN JWT into the target userspace so ALT-ELS authenticates.

CloudLinux 9 serves the Selector runtimes - alt-php, alt-python, alt-ruby,
alt-nodejs - from the main CloudLinux channel: `repoquery alt-php81` on a CL9 box
answers cl-channel. CloudLinux 10 serves them from per-language ALT-ELS
repositories instead, which leapp-data declares for the el10 target.

Those repositories authenticate with the CLN JWT. rhn-client-tools symlinks
/etc/dnf/vars/phpelstoken and its three siblings to /etc/sysconfig/rhn/jwt.token
(cl_post_jwt_update.py), so all four variables are one token. leapp copies only
/etc/dnf/dnf.conf into the target userspace, so without this the variables resolve
to nothing there, every ELS repository 401s, and the upgrade completes leaving
alt-php at its el9 build with no repository to update from - 12076 packages,
covering alt-php53 through alt-php86, unreachable.

The release packages are installed too, so the booted system keeps its own
repofiles. They have to be the el10 builds: the el9 els-php-release hardcodes
el/9 in its baseurl, and only the el10 one uses $releasever, so carrying the el9
package across leaves a CloudLinux 10 box pointed at el9 PHP content.

A box with no JWT - unregistered, or IP-licensed without a completed
registration - produces nothing here. Copying a path that does not exist fails
the userspace build, and such a system must still upgrade; skip_if_unavailable on
the repositories is what lets it, just without ELS content.
"""

import os

from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import (
    CopyFile,
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RpmTransactionTasks,
    TargetUserSpacePreupgradeTasks,
)

# The first CloudLinux target that serves the Selector runtimes from ALT-ELS
# rather than from the main CloudLinux channel.
FIRST_MAJOR_USING_ELS = 10

JWT_TOKEN = '/etc/sysconfig/rhn/jwt.token'
DNF_VARS_DIR = '/etc/dnf/vars'

# All four are symlinks to JWT_TOKEN. They are copied individually rather than
# as a directory because /etc/dnf/vars also holds unrelated variables whose
# values are source-specific.
ELS_DNF_VARS = (
    'phpelstoken',
    'altpythonelstoken',
    'altrubyelstoken',
    'altnodejselstoken',
)

# The ALT-ELS repositories live in their own repofile, which leapp-data installs
# beside the main one but which nothing scans automatically. scancustomrepofile
# emits a CustomTargetRepository for every section of
# /etc/leapp/files/leapp_upgrade_repositories.repo, unconditionally - so a
# repository named there becomes a target repository whatever its enabled flag
# says and whatever the repomap does. Measured twice on an unregistered box:
# these then answer 403 with $phpelstoken unexpanded and the target userspace
# build dies on the metadata download, which skip_if_unavailable does not absorb.
#
# Pulling the file in here instead makes the token the only gate: no JWT, no
# repofile, no repositories.
ELS_REPO_FILE = '/etc/leapp/files/cloudlinux-els.repo'

_ELS_REPO_IDS = (
    'el10-php-els',
    'el10-alt-python',
    'el10-alt-ruby',
    'el10-alt-nodejs',
)

ELS_TARGET_REPOS = _ELS_REPO_IDS

ELS_RELEASE_PACKAGES = (
    'els-php-release',
    'els-python-release',
    'els-ruby-release',
    'els-nodejs-release',
)


def process():
    if int(get_target_major_version()) < FIRST_MAJOR_USING_ELS:
        return

    if not os.path.exists(JWT_TOKEN):
        api.current_logger().info(
            'No CLN JWT at %s, so the ALT-ELS repositories cannot authenticate.'
            ' Skipping - the upgrade proceeds without Selector runtime content.',
            JWT_TOKEN,
        )
        return

    copy_files = [CopyFile(src=JWT_TOKEN, dst=JWT_TOKEN)]
    for var in ELS_DNF_VARS:
        path = os.path.join(DNF_VARS_DIR, var)
        if os.path.exists(path):
            copy_files.append(CopyFile(src=path, dst=path))
        else:
            api.current_logger().debug(
                'ALT-ELS dnf variable %s is absent; its repository will be skipped.',
                path,
            )

    api.produce(TargetUserSpacePreupgradeTasks(copy_files=copy_files))
    api.produce(RpmTransactionTasks(to_install=list(ELS_RELEASE_PACKAGES)))
    if os.path.isfile(ELS_REPO_FILE):
        api.produce(CustomTargetRepositoryFile(file=ELS_REPO_FILE))
        for repoid in ELS_TARGET_REPOS:
            api.produce(CustomTargetRepository(repoid=repoid, enabled=True))
    else:
        api.current_logger().warning(
            '%s is absent, so the ALT-ELS repositories cannot be configured.'
            ' The Selector runtimes will stay at their source-major builds.',
            ELS_REPO_FILE,
        )
