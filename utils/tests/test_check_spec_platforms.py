import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, '..', 'check-spec-platforms.py')
_SPEC = os.path.join(_HERE, '..', '..', 'packaging', 'leapp-repository.spec')


def _load():
    spec = importlib.util.spec_from_file_location('check_spec_platforms', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load()


_MAKEFILE = os.path.join(_HERE, '..', '..', 'Makefile')


def test_the_source_tarball_bundles_deps_for_every_build_the_spec_defines():
    # Each build copies leapp*deps*el<next major> out of deps-pkgs.tar.gz, and
    # `make source` builds that tarball: DIST_VERSION=N produces the el(N+1) deps.
    with open(_SPEC) as fp:
        spec = fp.read()
    with open(_MAKEFILE) as fp:
        makefile = fp.read()
    assert check.missing_deps_bundles(spec, makefile) == []


def test_a_build_whose_deps_are_not_bundled_is_reported():
    spec = '%define next_major_ver 8\n%define next_major_ver 9\n%define next_major_ver 10\n'
    makefile = ('\t@$(MAKE) DIST_VERSION=7 _build_subpkg\n'
                '\t@$(MAKE) DIST_VERSION=9 _build_subpkg\n')
    # Builds need el8, el9 and el10 deps; 7 and 9 bundle el8 and el10, so el9's is missing.
    assert check.missing_deps_bundles(spec, makefile) == [8]


def test_a_spec_with_no_next_major_is_an_error_not_a_pass():
    with pytest.raises(check.UnknownCondition):
        check.missing_deps_bundles('Name: x\n', '\t@$(MAKE) DIST_VERSION=7 _build_subpkg\n')


_ROOT = os.path.join(_HERE, '..', '..')


def test_the_tree_ships_no_file_leapp_data_installs():
    # Both RPMs owning one path with different content is a transaction check error:
    # leapp-upgrade and leapp-data-cloudlinux could not be installed together.
    assert check.files_leapp_data_owns(_ROOT) == []


def test_a_key_under_the_leapp_data_tree_is_reported(tmp_path):
    keys = tmp_path.joinpath(*check.LEAPP_DATA_OWNED.split(os.sep), '9')
    keys.mkdir(parents=True)
    (keys / 'RPM-GPG-KEY-CloudLinux').write_text('key')
    found = check.files_leapp_data_owns(str(tmp_path))
    assert [os.path.basename(f) for f in found] == ['RPM-GPG-KEY-CloudLinux']


def test_no_such_tree_is_clean(tmp_path):
    assert check.files_leapp_data_owns(str(tmp_path)) == []
