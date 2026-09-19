import pytest

from leapp.libraries.common import detectcontrolpanel as dcp


@pytest.mark.parametrize('panel', [dcp.CPANEL_NAME, dcp.DIRECTADMIN_NAME, dcp.PLESK_NAME])
@pytest.mark.parametrize('target_major', ['8', '9'])
def test_supported_panels_do_not_block_up_to_cl9(panel, target_major):
    """cPanel, DirectAdmin and Plesk are supported targets on CL8 and CL9."""
    assert dcp.panel_blocks_upgrade(panel, target_major) is False


@pytest.mark.parametrize('panel', [dcp.CPANEL_NAME, dcp.DIRECTADMIN_NAME, dcp.PLESK_NAME])
def test_supported_panels_block_on_cl10(panel):
    """No control panel supports CloudLinux 10 yet, so all of them block it.

    This is the case the previous code got wrong: it asked "is this panel one we
    know about" rather than "is this panel supported on the target", so a cPanel
    host would have been allowed to upgrade to a release cPanel cannot run on.
    """
    assert dcp.panel_blocks_upgrade(panel, '10') is True


@pytest.mark.parametrize('panel', [dcp.NOPANEL_NAME, dcp.INTEGRATED_NAME, dcp.UNKNOWN_NAME])
@pytest.mark.parametrize('target_major', ['8', '9', '10'])
def test_absent_panel_never_blocks(panel, target_major):
    """No panel, the integrated panel and an undetectable one are not panels.

    'Unknown (legacy)' means detection could not tell, not that a panel is
    present, and it has never blocked; CL10 does not change that.
    """
    assert dcp.panel_blocks_upgrade(panel, target_major) is False


@pytest.mark.parametrize('target_major', ['8', '9', '10'])
def test_unsupported_panel_always_blocks(target_major):
    """A panel we have no data for blocks every target, as it always has."""
    assert dcp.panel_blocks_upgrade(dcp.ISPMANAGER_NAME, target_major) is True
    assert dcp.panel_blocks_upgrade(dcp.INTERWORX_NAME, target_major) is True


def test_cl10_answer_differs_from_cl9():
    """Pin that the target version actually changes the answer."""
    assert (
        dcp.panel_blocks_upgrade(dcp.CPANEL_NAME, '9')
        != dcp.panel_blocks_upgrade(dcp.CPANEL_NAME, '10')
    )
