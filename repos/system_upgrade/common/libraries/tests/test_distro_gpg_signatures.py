import json
import os

import pytest

_FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'files', 'distro')


# Distros whose data upstream migrated, plus ours. ol, rocky and scientific are
# upstream's and still carry the old list shape; they would fail the same way if
# anyone upgraded them, but inventing gpg-pubkey names for keys we cannot inspect
# would be worse than leaving them as upstream ships them.
_MIGRATED_DISTROS = ('almalinux', 'centos', 'cloudlinux', 'rhel')


def _distro_dirs():
    root = os.path.normpath(_FILES)
    return [d for d in _MIGRATED_DISTROS
            if os.path.isfile(os.path.join(root, d, 'gpg-signatures.json'))]


@pytest.mark.parametrize('distro', _distro_dirs())
def test_keys_is_a_mapping(distro):
    """`keys` must be a dict of key id -> gpg-pubkey package names.

    get_distribution_data() merges vendor signatures in with
    distro_config_json["keys"][sig] = [], and removeobsoletegpgkeys reads
    keys.values(). A list - the shape this file used to have - raises
    TypeError: list indices must be integers or slices, not str, straight out of
    an actor. That is what killed distribution_signed_rpm_scanner on the first
    CL9 -> CL10 run.
    """
    path = os.path.join(os.path.normpath(_FILES), distro, 'gpg-signatures.json')
    with open(path) as fp:
        data = json.load(fp)

    assert isinstance(data.get('keys'), dict), '{}: keys is {}'.format(
        distro, type(data.get('keys')).__name__)
    for key_id, packages in data['keys'].items():
        assert isinstance(key_id, str), distro
        assert isinstance(packages, list), '{}: {} maps to {}'.format(
            distro, key_id, type(packages).__name__)
