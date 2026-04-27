import os

import pytest

from leapp.libraries.common import cln_detect


@pytest.fixture
def clean_paths(monkeypatch, tmp_path):
    """Point cln_detect at a clean tmp dir so each test starts from no state."""
    systemid = tmp_path / "systemid"
    dnf_conf = tmp_path / "dnf_spacewalk.conf"
    yum_conf = tmp_path / "yum_spacewalk.conf"
    monkeypatch.setattr(cln_detect, "RHN_SYSTEMID", str(systemid))
    monkeypatch.setattr(cln_detect, "SPACEWALK_DNF_CONF", str(dnf_conf))
    monkeypatch.setattr(cln_detect, "SPACEWALK_YUM_CONF", str(yum_conf))
    return {"systemid": systemid, "dnf_conf": dnf_conf, "yum_conf": yum_conf}


def _touch(path, content=""):
    path.write_text(content)


def test_no_systemid_means_no_cln(clean_paths):
    # Without /etc/sysconfig/rhn/systemid the system is not registered with CLN.
    assert cln_detect.is_cln_configured() is False


def test_systemid_but_no_plugin_means_no_cln(clean_paths):
    _touch(clean_paths["systemid"])
    assert cln_detect.is_cln_configured() is False


def test_systemid_and_enabled_dnf_plugin_means_cln(clean_paths):
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    assert cln_detect.is_cln_configured() is True


def test_explicit_disabled_dnf_plugin_means_no_cln(clean_paths):
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 0\n")
    assert cln_detect.is_cln_configured() is False


def test_explicit_disabled_yum_plugin_means_no_cln(clean_paths):
    _touch(clean_paths["systemid"])
    _touch(clean_paths["yum_conf"], "[main]\nenabled=0\n")
    assert cln_detect.is_cln_configured() is False


def test_one_plugin_disabled_one_not_means_no_cln(clean_paths):
    # If either plugin config disables it, CLN is not usable.
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    _touch(clean_paths["yum_conf"], "[main]\nenabled = 0\n")
    assert cln_detect.is_cln_configured() is False


def test_plugin_conf_without_enabled_key_means_cln(clean_paths):
    # A plugin config that doesn't mention `enabled` defaults to enabled upstream,
    # so we must treat it as CLN active.
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\ntimeout = 120\n")
    assert cln_detect.is_cln_configured() is True


def test_comments_and_blank_lines_ignored(clean_paths):
    _touch(clean_paths["systemid"])
    _touch(
        clean_paths["dnf_conf"],
        "# some comment\n\n[main]\n# enabled = 0\nenabled = 1\n",
    )
    assert cln_detect.is_cln_configured() is True
