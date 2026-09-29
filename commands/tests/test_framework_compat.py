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


# 6.0's add_option forwards a default only `if default:`, so a falsy one - [] above
# all - never reaches argparse and the option arrives as None. 6.2 checks
# `is not None`. Code that relies on default=[] works on 6.2 and crashes on 6.0:
# `set(args.enable_experimental_feature)` took down every `leapp preupgrade` on CL7.
_FALSY = (ast.List, ast.Tuple, ast.Dict, ast.Set)


def _falsy_literal(node):
    if isinstance(node, _FALSY):
        return not getattr(node, 'elts', None) and not getattr(node, 'keys', None)
    value = getattr(node, 'value', getattr(node, 'n', getattr(node, 's', None)))
    return isinstance(node, (ast.Constant, ast.Num, ast.Str, ast.NameConstant)) and not value \
        and value is not None


def test_no_command_opt_relies_on_a_falsy_default():
    offenders = []
    for path in _sources():
        with open(path) as fp:
            tree = ast.parse(fp.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_command_opt(node):
                if any(kw.arg == 'default' and _falsy_literal(kw.value) for kw in node.keywords):
                    offenders.append('{0}:{1}'.format(os.path.relpath(path, COMMANDS_DIR), node.lineno))
    assert not offenders, (
        'leapp-framework 6.0 drops a falsy command_opt default, so the option is None there;'
        ' normalise it where it is read instead: {0}'.format(offenders)
    )


@pytest.mark.parametrize('cmd', [upgrade_cmd, preupgrade_cmd], ids=['upgrade', 'preupgrade'])
def test_prepare_configuration_accepts_what_6_0_passes(cmd, monkeypatch):
    from leapp.cli.commands import command_utils
    from leapp.cli.commands.upgrade import util

    parser = argparse.ArgumentParser()
    cmd.command.apply_parser(None, parser=parser)
    args = parser.parse_args([])
    # What 6.0 hands over for an unused append option, whatever default was declared.
    args.enable_experimental_feature = None
    args.whitelist_experimental = None

    monkeypatch.setattr(os, 'environ', dict(os.environ))
    monkeypatch.setattr(command_utils, 'get_source_distro_id', lambda: 'cloudlinux')
    monkeypatch.setattr(command_utils, 'get_target_release', lambda _args: ('8.10', 'default'))
    monkeypatch.setattr(command_utils, 'get_os_release_version_id', lambda _path: '7.9')

    configuration = util.prepare_configuration(args)
    assert list(configuration['whitelist_experimental']) == []
    assert os.environ['LEAPP_EXPERIMENTAL'] == '0'
