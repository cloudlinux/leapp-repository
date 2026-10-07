"""The CLI's own calls into command_utils, and the confirmation prompt they serve.

Resolving the 0.24.0 merge kept upstream's get_source_distro_id() and dropped our
get_os_release_id(filepath), while ask_to_continue - CloudLinux's own prompt,
shown by every interactive 'leapp upgrade' on CloudLinux - still called the old
name. Every such upgrade then died with an AttributeError before it started.
QA runs 'leapp upgrade --nowarn', which skips the prompt, so nothing caught it.
"""
import ast
import os

import pytest

from leapp.cli.commands import command_utils
from leapp.cli.commands.upgrade import util

_COMMANDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def _references():
    """(file, line, name) for every `command_utils.<name>` in the commands tree."""
    found = []
    for root, _dirs, files in os.walk(_COMMANDS):
        if os.sep + 'tests' in root[len(_COMMANDS):]:
            continue
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(root, name)
            with open(path) as fp:
                tree = ast.parse(fp.read(), path)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id == 'command_utils'):
                    found.append((os.path.relpath(path, _COMMANDS), node.lineno, node.attr))
    return found


def test_every_command_utils_reference_exists():
    missing = ['{0}:{1}: command_utils.{2}'.format(*ref) for ref in _references()
               if not hasattr(command_utils, ref[2])]
    assert missing == []


def _os_release(monkeypatch, os_id):
    monkeypatch.setattr(command_utils, '_retrieve_os_release_contents',
                        lambda *a, **k: {'ID': os_id, 'VERSION_ID': '8.10'})


def test_the_prompt_is_skipped_off_cloudlinux(monkeypatch):
    _os_release(monkeypatch, 'almalinux')
    monkeypatch.setattr(util.six.moves, 'input', lambda _prompt: pytest.fail('prompted'))

    assert util.ask_to_continue() is True


@pytest.mark.parametrize('answer, expected', [('y', True), ('N', False)])
def test_cloudlinux_asks_for_confirmation(monkeypatch, answer, expected):
    _os_release(monkeypatch, 'cloudlinux')
    monkeypatch.setattr(util.six.moves, 'input', lambda _prompt: answer)

    assert util.ask_to_continue() is expected
