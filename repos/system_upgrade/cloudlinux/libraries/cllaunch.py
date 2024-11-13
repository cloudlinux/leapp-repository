import functools
from leapp.libraries.common.config import version

def run_on_cloudlinux(func_or_version=None):
    """
    Decorator that runs a function only on specified CloudLinux versions.

    Can be used as:
        @run_on_cloudlinux              # Runs on any CloudLinux version
        @run_on_cloudlinux('7')         # Runs only on CloudLinux 7
        @run_on_cloudlinux(['7', '8'])  # Runs on CloudLinux 7 or 8
    """

    # If used without parentheses
    if callable(func_or_version):
        @functools.wraps(func_or_version)
        def direct_wrapper(*args, **kwargs):
            if version.current_version()[0] != "cloudlinux":
                return None
            return func_or_version(*args, **kwargs)
        return direct_wrapper

    # If used with version specification
    versions = func_or_version
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            release_id, version_id = version.current_version()

            # Check if running on CloudLinux
            if release_id != "cloudlinux":
                return None

            # If no versions specified, run on any CloudLinux version
            if versions is None:
                return func(*args, **kwargs)

            # Convert versions to list if string was provided
            version_list = [versions] if isinstance(versions, str) else versions

            # Compare only major version number
            current_major = version.get_major_version(version_id)
            if current_major in version_list:
                return func(*args, **kwargs)

            return None

        return wrapper
    return decorator
