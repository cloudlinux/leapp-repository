try:
    import ConfigParser as configparser  # py2
    ParserClass = configparser.SafeConfigParser
except ImportError:
    import configparser  # py3
    ParserClass = configparser.ConfigParser

from leapp.libraries.actor.enableyumspacewalkplugin import _enable_plugin


def _write(tmp_path, body):
    p = tmp_path / "spacewalk.conf"
    p.write_text(body)
    return str(p)


def test_missing_config_is_silent_skip(tmp_path):
    """Config file absent -> silent skip: no change, no title, no report.

    On no-auth systems (CLOS-4056) the dnf-plugin-spacewalk
    package is Obsoleted by rhn-client-tools >= 3.0.1.
    Emitting a 'not found' report there would be noise.
    """
    changed, title = _enable_plugin(str(tmp_path / "absent.conf"), ParserClass)
    assert changed is False
    assert title is None


def test_flips_enabled_zero_to_one(tmp_path):
    """Config present with enabled=0 -> flipped to 1, changed=True, no title."""
    cfg = _write(tmp_path, "[main]\nenabled = 0\n")
    changed, title = _enable_plugin(cfg, ParserClass)
    assert changed is True
    assert title is None
    updated = open(cfg).read()
    # ConfigParser may write either 'enabled = 1' or 'enabled=1'; accept both.
    assert "enabled = 1" in updated or "enabled=1" in updated


def test_already_enabled_is_noop(tmp_path):
    """Config present with enabled=1 -> no change, no title, file untouched."""
    cfg = _write(tmp_path, "[main]\nenabled = 1\n")
    original = open(cfg).read()
    changed, title = _enable_plugin(cfg, ParserClass)
    assert changed is False
    assert title is None
    assert open(cfg).read() == original


def test_missing_main_section_returns_config_error(tmp_path):
    """Config present but missing [main] -> title reports config error."""
    cfg = _write(tmp_path, "[other]\nenabled = 0\n")
    changed, title = _enable_plugin(cfg, ParserClass)
    assert changed is False
    assert title is not None
    assert "config error" in title.lower()
