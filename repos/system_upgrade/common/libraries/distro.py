import json
import os

from leapp.exceptions import StopActorExecutionError
from leapp.libraries.common import efi, repofileutils, rhsm
from leapp.libraries.common.config import get_target_distro_id
from leapp.libraries.common.config.architecture import ARCH_ACCEPTED, ARCH_X86_64
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import VendorSignatures


def get_distribution_data(distribution):
    distributions_path = api.get_common_folder_path('distro')

    distribution_config = os.path.join(distributions_path, distribution, 'gpg-signatures.json')
    if os.path.exists(distribution_config):
        with open(distribution_config) as distro_config_file:
            distro_config_json = json.load(distro_config_file)
    else:
        raise StopActorExecutionError(
            'Cannot find distribution signature configuration.',
            details={'Problem': 'Distribution {} was not found in {}.'.format(distribution, distributions_path)})

    # Extend with Vendors signatures
    for siglist in api.consume(VendorSignatures):
        for sig in siglist.sigs:
            # Add vendor signature as a new key with empty package list
            distro_config_json["keys"][sig] = []

    return distro_config_json

# distro -> major_version -> repofile -> tuple of architectures where it's present
_DISTRO_REPOFILES_MAP = {
    'rhel': {
        '8': {'/etc/yum.repos.d/redhat.repo': ARCH_ACCEPTED},
        '9': {'/etc/yum.repos.d/redhat.repo': ARCH_ACCEPTED},
        '10': {'/etc/yum.repos.d/redhat.repo': ARCH_ACCEPTED},
    },
    'centos': {
        '8': {
            # TODO is this true on all archs?
            'CentOS-Linux-AppStream.repo': ARCH_ACCEPTED,
            'CentOS-Linux-BaseOS.repo': ARCH_ACCEPTED,
            'CentOS-Linux-ContinuousRelease.repo': ARCH_ACCEPTED,
            'CentOS-Linux-Debuginfo.repo': ARCH_ACCEPTED,
            'CentOS-Linux-Devel.repo': ARCH_ACCEPTED,
            'CentOS-Linux-Extras.repo': ARCH_ACCEPTED,
            'CentOS-Linux-FastTrack.repo': ARCH_ACCEPTED,
            'CentOS-Linux-HighAvailability.repo': ARCH_ACCEPTED,
            'CentOS-Linux-Media.repo': ARCH_ACCEPTED,
            'CentOS-Linux-Plus.repo': ARCH_ACCEPTED,
            'CentOS-Linux-PowerTools.repo': ARCH_ACCEPTED,
            'CentOS-Linux-Sources.repo': ARCH_ACCEPTED,
        },
        '9': {
            '/etc/yum.repos.d/centos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/centos-addons.repo': ARCH_ACCEPTED,
        },
        '10': {
            '/etc/yum.repos.d/centos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/centos-addons.repo': ARCH_ACCEPTED,
        },
    },
    # CloudLinux. Contents taken from the cloudlinux-release package of each
    # target: it is that package which drops these files, and what it drops
    # changed at 10.
    #
    # On 8 and 9, cloudlinux-release owns the almalinux-*.repo files itself -
    # CloudLinux rebranded the base. On 10 it ships only cloudlinux.repo and
    # cloudlinux-rollout.repo, because CloudLinux 10 is layered on stock
    # AlmaLinux and almalinux-release provides the rest. The AlmaLinux names are
    # listed for 10 all the same: whichever package installs them, their repoids
    # have to be found, and a file that is not present is skipped rather than
    # treated as an error.
    #
    # Deliberately absent everywhere: cloudlinux-rollout.repo, which
    # scan_rollout_repositories owns and which must not count as base content,
    # and cloudlinux-imunify360.repo, which is a product repository rather than
    # the distribution's.
    'cloudlinux': {
        '8': {
            '/etc/yum.repos.d/almalinux-appstream.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-baseos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-devel.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-extras.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-ha.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-powertools.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-resilientstorage.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/cloudlinux-compat.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/cloudlinux.repo': ARCH_ACCEPTED,
        },
        '9': {
            '/etc/yum.repos.d/almalinux-appstream.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-baseos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-crb.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-devel.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/cloudlinux.repo': ARCH_ACCEPTED,
        },
        '10': {
            # no resilientstorage on 10, as with almalinux above
            '/etc/yum.repos.d/almalinux-appstream.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-baseos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-crb.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-extras.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-highavailability.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/cloudlinux.repo': ARCH_ACCEPTED,
        },
    },
    'almalinux': {
        '8': {
            # TODO is this true on all archs?
            '/etc/yum.repos.d/almalinux-ha.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-nfv.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-plus.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-powertools.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-resilientstorage.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-rt.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-sap.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-saphana.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux.repo': ARCH_ACCEPTED,
        },
        '9': {
            '/etc/yum.repos.d/almalinux-appstream.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-baseos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-crb.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-extras.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-highavailability.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-plus.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-resilientstorage.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-sap.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-saphana.repo': ARCH_ACCEPTED,
            # RT and NFV are only on x86_64 on almalinux 9
            '/etc/yum.repos.d/almalinux-nfv.repo': (ARCH_X86_64,),
            '/etc/yum.repos.d/almalinux-rt.repo': (ARCH_X86_64,),
        },
        '10': {
            # no resilientstorage on 10
            '/etc/yum.repos.d/almalinux-appstream.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-baseos.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-crb.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-extras.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-highavailability.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-plus.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-sap.repo': ARCH_ACCEPTED,
            '/etc/yum.repos.d/almalinux-saphana.repo': ARCH_ACCEPTED,
            # RT and NFV are only on x86_64 on almalinux 10
            '/etc/yum.repos.d/almalinux-nfv.repo': (ARCH_X86_64,),
            '/etc/yum.repos.d/almalinux-rt.repo': (ARCH_X86_64,),
        },
    },
}


def _get_distro_repofiles(distro, major_version, arch):
    """
    Get distribution provided repofiles.

    Note that this does not perform any validation, the caller must check
    whether the files exist.

    :param distro: The distribution to get repofiles for.
    :type distro: str
    :param major_version: The major version to get repofiles for.
    :type major_version: str
    :param arch: The architecture to get repofiles for.
    :type arch: str
    :return: A list of paths to repofiles provided by distribution
    :rtype: list[str] or None if no repofiles are mapped for the arguments
    """

    distro_repofiles = _DISTRO_REPOFILES_MAP.get(distro)
    if not distro_repofiles:
        return None

    version_repofiles = distro_repofiles.get(major_version, {})
    if not version_repofiles:
        return None

    return [repofile for repofile, archs in version_repofiles.items() if arch in archs]


def get_target_distro_repoids(context):
    """
    Get repoids defined in distro provided repofiles

    See the generic :func:`_get_distro_repoids` for more details.

    :param context: An instance of mounting.IsolatedActions class
    :type context: mounting.IsolatedActions
    :return: Repoids of distribution provided repositories
    :type: list[str]
    """

    return get_distro_repoids(
        context,
        get_target_distro_id(),
        get_target_major_version(),
        api.current_actor().configuration.architecture
    )


def get_distro_repoids(context, distro, major_version, arch):
    """
    Get repoids defined in distro provided repofiles

    On RHEL with RHSM this delegates to rhsm.get_available_repo_ids.

    Repofiles installed by RHUI client packages are not covered by this
    function.

    :param context: An instance of mounting.IsolatedActions class
    :type context: mounting.IsolatedActions
    :param distro: The distro whose repoids to return
    :type distro: str
    :param major_version: The major version to get distro repoids for.
    :type major_version: str
    :param arch: The architecture to get distro repoids for.
    :type arch: str
    :return: Repoids of distribution provided repositories
    :type: list[str]
    """

    if distro == 'rhel':
        if rhsm.skip_rhsm():
            return []
        # Kept this todo here from the original code from
        # userspacegen._get_rh_available_repoids:
        # Get the RHSM repos available in the target RHEL container
        # TODO: very similar thing should happens for all other repofiles in container
        return rhsm.get_available_repo_ids(context)

    try:
        repofiles = repofileutils.get_parsed_repofiles(context)
    except repofileutils.InvalidRepoDefinition as e:
        raise StopActorExecutionError(
            message="Failed to get distro provided repositories: {}".format(str(e)),
            details={
                'hint': 'Ensure the repository definition is correct or remove it '
                        'if the repository is not needed anymore. '
                        'This issue is typically caused by missing definition of the name field. '
                        'For more information, see: https://access.redhat.com/solutions/6969001.'
            })

    distro_repofiles = _get_distro_repofiles(distro, major_version, arch)
    if not distro_repofiles:
        # TODO: a different way of signaling an error would be preferred (e.g. returning None),
        # but since rhsm.get_available_repo_ids also raises StopActorExecutionError,
        # let's make it easier for the caller for now and use it too
        raise StopActorExecutionError(
            "No known distro provided repofiles mapped",
            details={
                "details": "distro: {}, major version: {}, architecture: {}".format(
                    distro, major_version, arch
                )
            },
        )

    distro_repoids = []
    for rfile in repofiles:
        if rfile.file in distro_repofiles:

            if not os.path.exists(context.full_path(rfile.file)):
                api.current_logger().debug(
                    "Expected distribution provided repofile does not exists: {}".format(
                        rfile
                    )
                )
                continue

            if rfile.data:
                distro_repoids.extend([repo.repoid for repo in rfile.data])

    return sorted(distro_repoids)


def distro_id_to_pretty_name(distro_id):
    """
    Get pretty name for the given distro id.

    The pretty name is what is found in the NAME field of /etc/os-release.
    """
    return {
        "rhel": "Red Hat Enterprise Linux",
        "centos": "CentOS Stream",
        "almalinux": "AlmaLinux",
    }[distro_id]


def get_distro_efidir_canon_path(distro_id):
    """
    Get canonical path to the distro EFI directory in the EFI mountpoint.

    NOTE: The path might be incorrect for distros not properly enabled for IPU,
    when enabling new distros in the codebase, make sure the path is correct.
    """
    if distro_id == "rhel":
        return os.path.join(efi.EFI_MOUNTPOINT, "EFI", "redhat")

    if distro_id == "almalinux":
        return os.path.join(efi.EFI_MOUNTPOINT, "EFI", "almalinux")

    if distro_id == "centos":
        return os.path.join(efi.EFI_MOUNTPOINT, "EFI", "centos")

    return os.path.join(efi.EFI_MOUNTPOINT, "EFI", distro_id)
