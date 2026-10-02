"""The one place that decides whether a kernel command line asks for cgroups-v1."""

# The values upstream's inhibit_cgroupsv1 has always treated as an opt-out.
_LEGACY_VALUES = ('0', 'false', 'no')


def requests_legacy_hierarchy(parameters):
    """
    Whether the kernel parameters ask systemd for the legacy (cgroups-v1) hierarchy.

    The unified hierarchy is the default from RHEL 9 on, so only an explicit
    systemd.unified_cgroup_hierarchy opt-out counts.

    :param parameters: KernelCmdlineArg-like objects, e.g. KernelCmdline.parameters
    """
    for param in parameters:
        if param.key != 'systemd.unified_cgroup_hierarchy' or param.value is None:
            continue
        if param.value.lower() in _LEGACY_VALUES:
            return True
    return False
