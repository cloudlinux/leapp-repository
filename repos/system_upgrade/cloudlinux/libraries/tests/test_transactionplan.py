import ast
import os

from leapp.libraries.common.transactionplan import removed_without_successor
from leapp.models import FilteredRpmTransactionTasks


def _tasks(to_remove=(), to_install=()):
    return FilteredRpmTransactionTasks(to_remove=list(to_remove), to_install=list(to_install))


def _server_family(name):
    return name.split('-')[0].rstrip('0123456789.') if name.endswith('-server') else None


def test_removed_with_nothing_of_its_family_installed_is_reported():
    tasks = _tasks(to_remove=['mysql-server', 'mysql-libs'])
    assert removed_without_successor(tasks, ['mysql-server'], _server_family) == ['mysql-server']


def test_a_renamed_successor_of_the_same_family_carries_it():
    tasks = _tasks(to_remove=['mysql-server'], to_install=['mysql8.4-server'])
    assert removed_without_successor(tasks, ['mysql-server'], _server_family) == []


def test_a_successor_of_another_family_does_not_count():
    tasks = _tasks(to_remove=['mysql-server'], to_install=['mariadb-server'])
    assert removed_without_successor(tasks, ['mysql-server'], _server_family) == ['mysql-server']


def test_names_the_plan_keeps_are_not_reported():
    tasks = _tasks(to_remove=['mysql-libs'])
    assert removed_without_successor(tasks, ['mysql-server', 'mariadb-server'], _server_family) == []


def test_installs_outside_every_family_are_ignored():
    tasks = _tasks(to_remove=['mysql-server'], to_install=['httpd'])
    assert removed_without_successor(tasks, ['mysql-server'], _server_family) == ['mysql-server']


def test_results_are_sorted():
    tasks = _tasks(to_remove=['mysql-server', 'mariadb-server'])
    found = removed_without_successor(tasks, ['mysql-server', 'mariadb-server'], _server_family)
    assert found == ['mariadb-server', 'mysql-server']


def _actor_libraries():
    actors = os.path.join(os.path.dirname(__file__), '..', '..', 'actors')
    for root, _dirs, files in os.walk(actors):
        if os.path.basename(root) != 'libraries':
            continue
        for name in files:
            if name.endswith('.py'):
                yield os.path.join(root, name)


def _reads_to_remove(path):
    with open(path) as fp:
        tree = ast.parse(fp.read(), path)
    return any(isinstance(node, ast.Attribute) and node.attr == 'to_remove' for node in ast.walk(tree))


# The checks that inhibit on a lost package decide "lost" through this library.
# A second copy of the rule is how two checks come to disagree about one plan.
_CHECKS = ('checkclmysqltarget.py', 'checkdistrophptarget.py')


def test_the_lost_package_checks_do_not_decide_it_themselves():
    checks = [p for p in _actor_libraries() if os.path.basename(p) in _CHECKS]
    assert sorted(os.path.basename(p) for p in checks) == sorted(_CHECKS)
    assert [p for p in checks if _reads_to_remove(p)] == []
