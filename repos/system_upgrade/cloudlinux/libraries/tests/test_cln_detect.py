import pytest

from leapp.libraries.common import cln_detect
from leapp.libraries.stdlib import CalledProcessError


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


@pytest.fixture
def fake_rpm(monkeypatch):
    """Monkeypatch cln_detect.run with a fake `rpm -q --quiet <pkg>` driver.

    Tests mutate the returned set to declare which plugin packages should
    look installed; the fake `run` mirrors the real `rpm -q --quiet`
    semantics by raising CalledProcessError for non-installed packages.
    """
    installed = set()

    def _run(cmd, **kwargs):
        # We only expect cln_detect to call rpm in the single-package form;
        # if that contract changes the test should fail loudly rather than
        # silently lie.
        assert cmd[:3] == ['rpm', '-q', '--quiet'] and len(cmd) == 4, (
            "unexpected rpm invocation: %r" % (cmd,)
        )
        pkg = cmd[3]
        if pkg in installed:
            return {'exit_code': 0, 'stdout': '', 'stderr': ''}
        raise CalledProcessError(
            message='package %s is not installed' % pkg,
            command=cmd,
            result={'exit_code': 1, 'stdout': '', 'stderr': ''},
        )

    monkeypatch.setattr(cln_detect, "run", _run)
    return installed


def _touch(path, content=""):
    path.write_text(content)


def test_no_systemid_means_channel_inactive(clean_paths, fake_rpm):
    # Without registration the spacewalk plugin can't authenticate, so even
    # if the plugin is installed it is not the active package channel.
    fake_rpm.add('dnf-plugin-spacewalk')
    assert cln_detect.is_cln_package_channel_active() is False


def test_systemid_but_no_plugin_installed_means_channel_inactive(clean_paths, fake_rpm):
    # systemid is there and a plugin config file is even present, but no
    # spacewalk plugin RPM is installed. This is the rhn-client-tools 3.0+
    # Obsoletes left-behind-config case: helper must return False here,
    # otherwise CLN-assuming actors would mis-fire on a no-auth system.
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    assert cln_detect.is_cln_package_channel_active() is False


def test_systemid_but_no_plugin_conf_means_channel_inactive(clean_paths, fake_rpm):
    fake_rpm.add('dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    assert cln_detect.is_cln_package_channel_active() is False


def test_systemid_and_enabled_dnf_plugin_means_channel_active(clean_paths, fake_rpm):
    fake_rpm.add('dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    assert cln_detect.is_cln_package_channel_active() is True


def test_explicit_disabled_dnf_plugin_means_channel_inactive(clean_paths, fake_rpm):
    fake_rpm.add('dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 0\n")
    assert cln_detect.is_cln_package_channel_active() is False


def test_explicit_disabled_yum_plugin_means_channel_inactive(clean_paths, fake_rpm):
    fake_rpm.add('yum-rhn-plugin')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["yum_conf"], "[main]\nenabled=0\n")
    assert cln_detect.is_cln_package_channel_active() is False


def test_one_plugin_disabled_one_not_means_channel_inactive(clean_paths, fake_rpm):
    # If either plugin config disables the plugin, treat the channel as off.
    fake_rpm.add('dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    _touch(clean_paths["yum_conf"], "[main]\nenabled = 0\n")
    assert cln_detect.is_cln_package_channel_active() is False


def test_plugin_conf_without_enabled_key_means_channel_active(clean_paths, fake_rpm):
    # A plugin config that does not mention `enabled` defaults to enabled
    # upstream, so we must treat the channel as active.
    fake_rpm.add('dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\ntimeout = 120\n")
    assert cln_detect.is_cln_package_channel_active() is True


def test_comments_and_blank_lines_ignored(clean_paths, fake_rpm):
    fake_rpm.add('dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    _touch(
        clean_paths["dnf_conf"],
        "# some comment\n\n[main]\n# enabled = 0\nenabled = 1\n",
    )
    assert cln_detect.is_cln_package_channel_active() is True


def test_yum_plugin_alone_counts_as_installed(clean_paths, fake_rpm):
    # Only the YUM-side plugin package is installed (CL7 case); the helper
    # should still consider the channel potentially active.
    fake_rpm.add('yum-rhn-plugin')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["yum_conf"], "[main]\nenabled = 1\n")
    assert cln_detect.is_cln_package_channel_active() is True


def test_python3_plugin_package_alone_counts_as_installed(clean_paths, fake_rpm):
    # The python3- subpackage of the DNF plugin counts too.
    fake_rpm.add('python3-dnf-plugin-spacewalk')
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    assert cln_detect.is_cln_package_channel_active() is True


def test_rpm_call_oserror_falls_through_to_inactive(monkeypatch, clean_paths):
    # If rpm itself can't be invoked at all (broken PATH / db / etc.) the
    # helper should fail safe by reporting the channel as inactive. That
    # only makes CLN-assuming actors skip - the safe side of the call.
    def _run_raises_os(cmd, **kwargs):
        raise OSError(2, 'No such file or directory: rpm')

    monkeypatch.setattr(cln_detect, "run", _run_raises_os)
    _touch(clean_paths["systemid"])
    _touch(clean_paths["dnf_conf"], "[main]\nenabled = 1\n")
    assert cln_detect.is_cln_package_channel_active() is False
