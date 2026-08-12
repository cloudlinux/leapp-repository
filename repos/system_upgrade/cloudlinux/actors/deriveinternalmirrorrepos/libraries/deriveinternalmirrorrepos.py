from leapp.libraries.common.cl_repofileutils import create_leapp_repofile_copy
from leapp.libraries.common.config.version import get_target_major_version
from leapp.libraries.stdlib import api
from leapp.models import (
    CustomTargetRepository,
    CustomTargetRepositoryFile,
    RepositoriesFacts,
    RepositoryData,
    RepositoryFile,
)

RELEASEVER_VAR = '$releasever'

DERIVED_REPOFILE_NAME = 'internal_mirror'

# Source repository IDs we know how to retarget.
#
# Deliberately a closed list rather than "every repo with a $releasever":
# entries produced here become CustomTargetRepository messages, and those are
# *required* target repositories (see TargetRepositories.custom_repos). A
# third-party repo whose vendor has not published el9 content yet would
# therefore inhibit the upgrade rather than simply being skipped.
#
# These IDs are the ones used by the internal mirror this was written for,
# where the base OS is AlmaLinux with a CloudLinux overlay.
DERIVABLE_REPOIDS = frozenset((
    'cloudlinux-os',
    'cloudlinux-ea4',
    'almalinux-BaseOS',
    'almalinux-AppStream',
    'almalinux-PowerTools',
))

# Repository directory components renamed between el8 and el9. AlmaLinux
# renamed PowerTools to CRB in el9, while el8 repo files still refer to
# PowerTools. The mirror this was written for follows the upstream naming:
# its el9 AlmaLinux tree serves CRB, and the el9 PowerTools path answers 404.
COMPONENT_RENAMES = {
    'PowerTools': 'CRB',
}


def _rename_final_component(baseurl, renames):
    """
    Rename the last path component of a repository URL, if it was renamed
    between the source and target major versions.

    Only the final component is considered: the same word may legitimately
    appear earlier in a mirror path without referring to the repository.
    """
    stripped = baseurl.rstrip('/')
    head, _, last = stripped.rpartition('/')
    if last in renames:
        return '{}/{}'.format(head, renames[last])
    # Leave the URL exactly as it was, trailing slash included.
    return baseurl


def derive_target_baseurl(baseurl, target_major, renames=None):
    """
    Build the target-version baseurl from a source repository's baseurl.

    ``$basearch`` is intentionally left in place - dnf expands it inside the
    target userspace container.
    """
    if renames is None:
        renames = COMPONENT_RENAMES
    retargeted = baseurl.replace(RELEASEVER_VAR, target_major)
    return _rename_final_component(retargeted, renames)


def _is_derivable(repo):
    """
    A source repository can be retargeted only when it is one we recognise,
    is in use, and its baseurl is version-templated.
    """
    if repo.repoid not in DERIVABLE_REPOIDS:
        return False
    if not repo.enabled:
        return False
    if not repo.baseurl or RELEASEVER_VAR not in repo.baseurl:
        # A baseurl with the version hardcoded cannot be retargeted safely.
        api.current_logger().debug(
            'Repository {} has no {} in its baseurl, not deriving a target repository'.format(
                repo.repoid, RELEASEVER_VAR
            )
        )
        return False
    return True


def _derive_repo(repo, target_major):
    # Suffix the repoid so the derived repository cannot collide with the
    # source one of the same name inside the upgrade container.
    return RepositoryData(
        repoid='{}-{}'.format(repo.repoid, target_major),
        name='{} (el{}, derived from {})'.format(repo.name or repo.repoid, target_major, repo.repoid),
        baseurl=derive_target_baseurl(repo.baseurl, target_major),
        enabled=True,
    )


def process():
    target_major = get_target_major_version()

    derived = []
    for facts in api.consume(RepositoriesFacts):
        for repo_file in facts.repositories:
            for repo in repo_file.data:
                if _is_derivable(repo):
                    derived.append(_derive_repo(repo, target_major))

    if not derived:
        # Not an internal-mirror system - leave the standard mapping alone.
        return

    api.current_logger().debug(
        'Derived target repositories from the internal mirror: {}'.format(
            ', '.join('{} -> {}'.format(repo.repoid, repo.baseurl) for repo in derived)
        )
    )

    for repo in derived:
        api.produce(
            CustomTargetRepository(
                repoid=repo.repoid,
                name=repo.name,
                baseurl=repo.baseurl,
                enabled=repo.enabled,
            )
        )

    # The repoids above are only accepted if they actually resolve inside the
    # target userspace container, so ship a repofile carrying them too.
    repofile_path = create_leapp_repofile_copy(
        RepositoryFile(file=DERIVED_REPOFILE_NAME, data=derived), DERIVED_REPOFILE_NAME
    )
    api.produce(CustomTargetRepositoryFile(file=repofile_path))
