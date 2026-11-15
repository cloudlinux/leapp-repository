import pytest

from leapp.libraries.common import cgroups
from leapp.models import KernelCmdlineArg


def _args(*pairs):
    return [KernelCmdlineArg(key=key, value=value) for key, value in pairs]


@pytest.mark.parametrize('value', ['0', 'false', 'False', 'no'])
def test_legacy_requested(value):
    params = _args(('ro', None), ('systemd.unified_cgroup_hierarchy', value))
    assert cgroups.requests_legacy_hierarchy(params) is True


@pytest.mark.parametrize('params', [
    # The unified hierarchy is the default from RHEL 9 on, so only an explicit
    # opt-out counts.
    _args(('ro', None), ('quiet', None)),
    _args(('cgroup_no_v1', 'all')),
    _args(('systemd.unified_cgroup_hierarchy', '1')),
    _args(('systemd.unified_cgroup_hierarchy', 'true')),
    _args(('systemd.unified_cgroup_hierarchy', 'yes')),
    _args(('systemd.unified_cgroup_hierarchy', None)),
    # The legacy controller argument alone does not select the hierarchy.
    _args(('systemd.legacy_systemd_cgroup_controller', None)),
    [],
])
def test_legacy_not_requested(params):
    assert cgroups.requests_legacy_hierarchy(params) is False
