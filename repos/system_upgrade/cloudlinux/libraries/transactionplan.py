"""Questions asked of the settled RPM transaction plan.

The plan is FilteredRpmTransactionTasks: what leapp will remove and install once
every actor's requests are merged. Checks that inhibit because an upgrade would
lose a package decide "lost" here, so that two of them cannot disagree about the
same plan.
"""


def removed_without_successor(tasks, names, family):
    """The *names* that *tasks* removes while installing nothing of their family.

    *family* maps a package name to the key its successors share - mysql8.4-server
    carries mysql-server across - or to None for a name outside every family the
    caller watches. The result is sorted, so reports come out in a stable order.
    """
    installing = {family(name) for name in tasks.to_install} - {None}
    return [
        name for name in sorted(names)
        if name in tasks.to_remove and family(name) not in installing
    ]
