"""The CLI commands must load on leapp-framework 6.0, not only on 6.2.

el7's framework stops at python2-leapp 0.18.0 (leapp-framework 6.0), and
CloudLinux publishes nothing newer for el8 either. 6.0's command_opt hands its
keyword arguments straight to add_option, which has no 'aliases', so one
`command_opt(..., aliases=[...])` stops every leapp subcommand from loading:
"add_option() got an unexpected keyword argument 'aliases'". Upstream uses that
keyword freely, so each merge can bring it back - this module fails when it does.
command_utils.command_opt_with_aliases registers extra long forms in a way both
frameworks accept.
"""
import argparse
import ast
import os

import pytest

from leapp.cli.commands.preupgrade import preupgrade as preupgrade_cmd
from leapp.cli.commands.upgrade import upgrade as upgrade_cmd

COMMANDS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sources():
    for root, dirs, files in os.walk(COMMANDS_DIR):
        dirs[:] = [d for d in dirs if d not in ('tests', '__pycache__')]
        for name in files:
            if name.endswith('.py'):
                yield os.path.join(root, name)


def _is_command_opt(call):
    func = call.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, 'attr', None)
    return name == 'command_opt'


def test_no_command_opt_takes_aliases():
    offenders = []
    for path in _sources():
        with open(path) as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_command_opt(node):
                if any(kw.arg == 'aliases' for kw in node.keywords):
                    offenders.append('{0}:{1}'.format(os.path.relpath(path, COMMANDS_DIR), node.lineno))
    assert not offenders, (
        'command_opt(aliases=...) needs leapp-framework 6.2 and breaks the CLI on 6.0;'
        ' use command_utils.command_opt_with_aliases instead: {0}'.format(offenders)
    )


@pytest.mark.parametrize('cmd', [upgrade_cmd, preupgrade_cmd], ids=['upgrade', 'preupgrade'])
@pytest.mark.parametrize('flag', ['--target', '--target-version'])
def test_target_accepts_both_spellings(cmd, flag):
    parser = argparse.ArgumentParser()
    cmd.command.apply_parser(None, parser=parser)
    assert parser.parse_args([flag, '10.2']).target_version == '10.2'
