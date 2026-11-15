import os
import re

from leapp import reporting
from leapp.libraries.common.backup import backup_file_in_place, LEAPP_BACKUP_SUFFIX
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api

CL_MYSQL_REPO = '/etc/yum.repos.d/cl-mysql.repo'

# The CloudLinux 10 trees under other/cl10/mysqlmeta/ have no mysqlglobalrepo.
TARGETS_WITHOUT_GLOBAL_REPO = ('10',)

_SECTION = re.compile(r'^\s*\[([^\]]+)\]')
_GLOBAL_URL = re.compile(r'^\s*(?:baseurl|mirrorlist|metalink)\s*=.*/mysqlmeta/mysqlglobalrepo/')


def drop_global_sections(text):
    """`text` without the sections whose URL is the mysqlglobalrepo tree.

    Returns (new text, [dropped section ids]). Everything else - other sections,
    comments, spacing - is kept verbatim. A section is dropped up to the next
    section header, so the blank lines that separated it go with it.
    """
    sections = []  # [section id, or None for anything before the first header; [lines]]
    for line in text.splitlines(True):
        match = _SECTION.match(line)
        if match:
            sections.append([match.group(1), [line]])
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append([None, [line]])
    kept, dropped = [], []
    for repoid, lines in sections:
        if repoid is not None and any(_GLOBAL_URL.match(line) for line in lines):
            dropped.append(repoid)
        else:
            kept.extend(lines)
    return ''.join(kept), dropped


def process():
    if get_target_major_version() not in TARGETS_WITHOUT_GLOBAL_REPO:
        return
    if not os.path.isfile(CL_MYSQL_REPO):
        return
    with open(CL_MYSQL_REPO) as fp:
        text = fp.read()
    text, dropped = drop_global_sections(text)
    if not dropped:
        return
    backup_file_in_place(CL_MYSQL_REPO)
    with open(CL_MYSQL_REPO, 'w') as fp:
        fp.write(text)
    api.current_logger().info(
        'Dropped %s from %s: CloudLinux %s publishes no mysqlglobalrepo',
        ', '.join(dropped), CL_MYSQL_REPO, get_target_major_version())
    reporting.create_report([
        reporting.Title('Removed a MySQL Governor repository CloudLinux 10 does not publish'),
        reporting.Summary(
            'The repository {ids} in {path} pointed at mysqlmeta/mysqlglobalrepo, which'
            ' MySQL Governor uses on CloudLinux 8 and 9 for mysql.type=auto. CloudLinux 10'
            ' publishes no such repository, and left in place it would make every dnf command'
            ' fail. The original file is kept as {backup}.'.format(
                ids=', '.join(dropped), path=CL_MYSQL_REPO, backup=CL_MYSQL_REPO + LEAPP_BACKUP_SUFFIX)
        ),
        reporting.Severity(reporting.Severity.INFO),
        reporting.Groups([reporting.Groups.REPOSITORY]),
        reporting.Remediation(
            hint='If MySQL Governor should manage a database on this server, run'
                 ' "/usr/share/lve/dbgovernor/mysqlgovernor.py --mysql-version=<version>"'
                 ' and then "--install", which writes the repository for that version.'
        ),
    ])
