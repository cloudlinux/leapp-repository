import fnmatch
import os
import re

from leapp.libraries.common.config.version import get_source_major_version, get_target_major_version
from leapp.libraries.stdlib import api, CalledProcessError, run

REPO_DIR = '/etc/yum.repos.d'

# The release packages whose %post pins $releasever to `rpm -E %{rhel}`.
ELS_RELEASE_PACKAGES = ('els-*-release', 'alt-common-release')

_URL_LINE = re.compile(r'^\s*(?:baseurl|mirrorlist|metalink)\s*=')


def repin(text, source_major, target_major):
    """`text` with /el/<source_major>/ moved to /el/<target_major>/ in its URL lines.

    Returns (new text, number of lines changed). Only the bare major as a whole
    path segment moves: el/9.6, el/90 and el/$releasever are not what the %post
    writes, so they are not this actor's to change.
    """
    old = '/el/{0}/'.format(source_major)
    new = '/el/{0}/'.format(target_major)
    changed = 0
    lines = []
    for line in text.splitlines(True):
        if old in line and _URL_LINE.match(line):
            line = line.replace(old, new)
            changed += 1
        lines.append(line)
    return ''.join(lines), changed


def _els_release_packages():
    names = run(['rpm', '-qa', '--queryformat', '%{NAME}\n'], split=True)['stdout']
    return sorted(set(name for name in names
                      if any(fnmatch.fnmatch(name, pattern) for pattern in ELS_RELEASE_PACKAGES)))


def _owned_repofiles(package):
    paths = run(['rpm', '-ql', package], split=True)['stdout']
    return [path for path in paths
            if os.path.dirname(path) == REPO_DIR and path.endswith('.repo') and os.path.isfile(path)]


def process():
    source_major = get_source_major_version()
    target_major = get_target_major_version()
    try:
        packages = _els_release_packages()
    except CalledProcessError as exc:
        api.current_logger().warning('Could not list the installed packages: %s', exc)
        return
    for package in packages:
        try:
            repofiles = _owned_repofiles(package)
        except CalledProcessError as exc:
            api.current_logger().warning('Could not list the files of %s: %s', package, exc)
            continue
        for path in repofiles:
            with open(path) as fp:
                text = fp.read()
            text, changed = repin(text, source_major, target_major)
            if not changed:
                continue
            with open(path, 'w') as fp:
                fp.write(text)
            api.current_logger().info(
                'Moved %d repository URL(s) in %s (%s) from el/%s to el/%s',
                changed, path, package, source_major, target_major)
