try:
    import ConfigParser as configparser  # py2
    ParserClass = configparser.SafeConfigParser
except ImportError:
    import configparser  # py3
    ParserClass = configparser.ConfigParser

from leapp.libraries.actor.enableyumspacewalkplugin import _enable_plugin


def _installed():
    """Stand in for is_spacewalk_plugin_installed().

    Every test that exercises the config-editing path has to pass this. Without
    it _enable_plugin falls back to querying the rpmdb of whatever machine runs
    the suite, so the same test passes on a host with dnf-plugin-spacewalk and
    fails on one without - which is most of them, since rhn-client-tools 3.0+
    Obsoletes it.
    """
    return True


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
    changed, title = _enable_plugin(cfg, ParserClass, plugin_installed_fn=_installed)
    assert changed is True
    assert title is None
    updated = open(cfg).read()
    # ConfigParser may write either 'enabled = 1' or 'enabled=1'; accept both.
    assert "enabled = 1" in updated or "enabled=1" in updated


def test_already_enabled_is_noop(tmp_path):
    """Config present with enabled=1 -> no change, no title, file untouched."""
    cfg = _write(tmp_path, "[main]\nenabled = 1\n")
    original = open(cfg).read()
    changed, title = _enable_plugin(cfg, ParserClass, plugin_installed_fn=_installed)
    assert changed is False
    assert title is None
    assert open(cfg).read() == original


def test_missing_main_section_returns_config_error(tmp_path):
    """Config present but missing [main] -> title reports config error."""
    cfg = _write(tmp_path, "[other]\nenabled = 0\n")
    changed, title = _enable_plugin(cfg, ParserClass, plugin_installed_fn=_installed)
    assert changed is False
    assert title is not None
    assert "config error" in title.lower()


def test_leftover_config_without_plugin_is_skipped(tmp_path):
    """A config file with no plugin installed must not be re-enabled.

    rhn-client-tools 3.0+ Obsoletes dnf-plugin-spacewalk, and CloudLinux 10 ships
    no spacewalk plugin at all. A spacewalk.conf left behind by either - saved
    without an .rpmsave suffix, or preserved by hand - would otherwise be flipped
    back to enabled=1 for a plugin that cannot run. Same stale-config case
    cln_detect guards for the other CLN actors.
    """
    config = tmp_path / 'spacewalk.conf'
    config.write_text(u'[main]\nenabled = 0\n')

    changed, title = _enable_plugin(
        str(config), plugin_installed_fn=lambda: False
    )

    assert changed is False
    assert title is None
    assert 'enabled = 0' in config.read_text()


def test_config_with_plugin_installed_is_still_enabled(tmp_path):
    """The guard must not disable the actor where it is still needed."""
    config = tmp_path / 'spacewalk.conf'
    config.write_text(u'[main]\nenabled = 0\n')

    changed, title = _enable_plugin(
        str(config), plugin_installed_fn=lambda: True
    )

    assert changed is True
    assert title is None
    assert 'enabled = 1' in config.read_text()
