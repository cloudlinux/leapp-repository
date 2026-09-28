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


def _findings(text):
    return check.boolean_dependencies(text.splitlines(), rhel=7)


def test_the_shipped_spec_has_no_boolean_dependency_on_el7():
    # rpm 4.11 on CL7 stops at the first one, before a source RPM exists.
    with open(_SPEC) as fp:
        assert check.boolean_dependencies(fp.read().splitlines(), rhel=7) == []


def test_a_boolean_dependency_at_top_level_is_found():
    found = _findings('Name: x\nRequires: (a if b)\n')
    assert [line for _n, line in found] == ['Requires: (a if b)']


def test_one_after_a_comma_is_found_too():
    assert len(_findings('Requires: foo, (a if b)\n')) == 1


@pytest.mark.parametrize('tag', ['Recommends', 'Suggests', 'Supplements', 'Conflicts',
                                 'BuildRequires', 'Requires(post)'])
def test_every_dependency_tag_counts(tag):
    assert len(_findings('{0}: (a or b)\n'.format(tag))) == 1


def test_a_plain_dependency_is_not_one():
    assert _findings('Requires: leapp-framework >= 6.0, leapp-framework < 7\n') == []


def test_a_branch_el7_does_not_take_is_skipped():
    text = ('%if 0%{?rhel} != 7\nRequires: (a if b)\n%endif\n'
            '%if 0%{?rhel} == 7\nRequires: plain\n%else\nRequires: (c if d)\n%endif\n')
    assert _findings(text) == []


def test_the_branch_el7_takes_is_checked():
    text = '%if 0%{?rhel} == 7\nRequires: (a if b)\n%else\nRequires: plain\n%endif\n'
    assert len(_findings(text)) == 1


def test_compound_conditions_evaluate():
    text = '%if 0%{?rhel} && 0%{?rhel} == 7\nRequires: (a if b)\n%endif\n'
    assert len(_findings(text)) == 1


def test_nesting_inside_a_skipped_branch_stays_skipped():
    text = '%if 0%{?rhel} == 8\n%if 0%{?rhel}\nRequires: (a if b)\n%endif\n%endif\n'
    assert _findings(text) == []


def test_an_unknown_condition_el7_would_reach_is_an_error_not_a_guess():
    with pytest.raises(check.UnknownCondition):
        _findings('%if %{with foo}\nRequires: (a if b)\n%endif\n')


def test_an_unknown_condition_inside_a_skipped_branch_is_not_evaluated():
    assert _findings('%if 0%{?rhel} == 9\n%if %{with foo}\n%endif\n%endif\n') == []


def test_the_changelog_is_not_parsed():
    assert _findings('%changelog\n- Requires: (a if b) is now handled\n') == []


def test_unbalanced_conditionals_are_an_error():
    with pytest.raises(check.UnknownCondition):
        _findings('%if 0%{?rhel} == 7\nRequires: x\n')


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
