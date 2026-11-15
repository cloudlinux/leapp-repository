import pytest

from leapp.libraries.common import distro
from leapp.libraries.common.config.architecture import ARCH_X86_64


@pytest.mark.parametrize('major', ['8', '9', '10'])
def test_cloudlinux_has_repofiles_for_every_target(major):
    """Every CloudLinux target major needs an entry, or the upgrade errors out.

    get_distro_repoids raises StopActorExecutionError("No known distro provided
    repofiles mapped") when the map has nothing for (distro, major, arch) - which
    is what stopped the first CL9 -> CL10 run once it reached
    target_userspace_creator.
    """
    repofiles = distro._get_distro_repofiles('cloudlinux', major, ARCH_X86_64)
    assert repofiles, 'no repofiles mapped for cloudlinux {}'.format(major)


def test_cloudlinux_10_carries_no_almalinux_repofiles_of_its_own():
    """CloudLinux 10 stopped shipping the AlmaLinux repofiles.

    cloudlinux-release-10 provides only cloudlinux.repo and
    cloudlinux-rollout.repo - the AlmaLinux ones come from almalinux-release,
    because CL10 is layered on stock AlmaLinux rather than rebranding it. On 8 and
    9 cloudlinux-release owns the almalinux-*.repo files itself.
    """
    ten = distro._get_distro_repofiles('cloudlinux', '10', ARCH_X86_64)
    nine = distro._get_distro_repofiles('cloudlinux', '9', ARCH_X86_64)

    assert '/etc/yum.repos.d/cloudlinux.repo' in ten
    assert '/etc/yum.repos.d/almalinux-baseos.repo' in nine
    # Listed for 10 too: whichever package provides them, the container needs
    # their repoids found. A file that is not there is skipped, not an error.
    assert '/etc/yum.repos.d/almalinux-baseos.repo' in ten


def test_rollout_repofiles_are_not_treated_as_distro_repos():
    """Gradual-rollout repositories are deliberately out of the upgrade.

    scan_rollout_repositories handles them separately and they can carry packages
    newer than the PES data knows about, so they must not be counted among the
    distro-provided base repositories.
    """
    for major in ('8', '9', '10'):
        repofiles = distro._get_distro_repofiles('cloudlinux', major, ARCH_X86_64)
        assert not any('rollout' in f for f in repofiles), major
