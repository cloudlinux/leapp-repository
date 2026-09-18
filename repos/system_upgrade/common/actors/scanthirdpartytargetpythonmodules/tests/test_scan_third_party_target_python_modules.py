import os
from collections import defaultdict

import pytest

from leapp.libraries.actor import scanthirdpartytargetpythonmodules
from leapp.libraries.common.testutils import logger_mocked
from leapp.libraries.stdlib import api
from leapp.models import DistributionSignedRPM

SITE_PACKAGES = '/usr/lib/python3.9/site-packages'


@pytest.mark.parametrize('rhel_version,expected_python', [
    ('9', 'python3.9'),
    ('10', 'python3.12'),
    ('8', None),
    ('7', None),
    ('', None),
    ('invalid', None),
    (None, None),
])
def test_get_python_binary_for_rhel(rhel_version, expected_python):
    assert scanthirdpartytargetpythonmodules.get_python_binary_for_rhel(rhel_version) == expected_python


@pytest.mark.parametrize('file_name,parent_name,should_skip', [
    ('module.pyc', '__pycache__', True),
    ('module.pyc', 'site-packages', False),
    ('module.py', '__pycache__', False),
    ('module.so', '__pycache__', False),
    ('module.py', 'site-packages', False),
    ('module.so', 'site-packages', False),
])
def test_should_skip_file(file_name, parent_name, should_skip):
    path = os.path.join('/usr/lib/python3.9', parent_name, file_name)
    assert scanthirdpartytargetpythonmodules._should_skip_file(path) is should_skip


def test_scan_python_files(monkeypatch):
    system_paths = [SITE_PACKAGES]
    rpm_files = {
        '/usr/lib/python3.9/site-packages/rpm_module.py': 'rpm-package',
        '/usr/lib/python3.9/site-packages/another.py': 'another-rpm',
    }

    def mock_find_python_related(root):
        files = [
            os.path.join(SITE_PACKAGES, 'rpm_module.py'),
            os.path.join(SITE_PACKAGES, 'unowned.py'),
            os.path.join(SITE_PACKAGES, 'another.py'),
        ]
        return iter(files)

    monkeypatch.setattr(os.path, 'isdir', lambda path: True)
    monkeypatch.setattr(scanthirdpartytargetpythonmodules, 'find_python_related', mock_find_python_related)

    rpms_to_check, unowned = scanthirdpartytargetpythonmodules.scan_python_files(system_paths, rpm_files)

    assert 'rpm-package' in rpms_to_check
    assert 'another-rpm' in rpms_to_check
    assert '/usr/lib/python3.9/site-packages/unowned.py' in unowned
    assert len(unowned) == 1


@pytest.mark.parametrize('path_exists,mock_files', [
    (False, None),
    (True, ['/usr/lib/python3.9/site-packages/__pycache__/module.pyc']),
])
def test_scan_python_files_filtering(monkeypatch, path_exists, mock_files):
    system_paths = [SITE_PACKAGES]
    rpm_files = {}

    monkeypatch.setattr(os.path, 'isdir', lambda path: path_exists)

    if mock_files is not None:
        def mock_find_python_related(root):
            return iter(mock_files)
        monkeypatch.setattr(scanthirdpartytargetpythonmodules, 'find_python_related', mock_find_python_related)

    rpms_to_check, unowned = scanthirdpartytargetpythonmodules.scan_python_files(system_paths, rpm_files)

    assert len(rpms_to_check) == 0
    assert len(unowned) == 0


@pytest.mark.parametrize('is_signed,expected_rpm_count,expected_file_count', [
    (False, 1, 2),
    (True, 0, 0),
])
def test_identify_unsigned_rpms(monkeypatch, is_signed, expected_rpm_count, expected_file_count):
    rpms_to_check = defaultdict(list)
    package_name = 'test-package'
    rpms_to_check[package_name] = [
        '/path/to/file1.py',
        '/path/to/file2.py',
    ]

    def mock_has_package(model, pkg_name):
        return is_signed

    monkeypatch.setattr(scanthirdpartytargetpythonmodules, 'has_package', mock_has_package)
    monkeypatch.setattr(api, 'current_logger', logger_mocked())

    third_party_rpms, third_party_files = scanthirdpartytargetpythonmodules.identify_unsigned_rpms(rpms_to_check)

    assert len(third_party_rpms) == expected_rpm_count
    assert len(third_party_files) == expected_file_count

    if not is_signed:
        assert package_name in third_party_rpms
        assert '/path/to/file1.py' in third_party_files
        assert '/path/to/file2.py' in third_party_files


def test_identify_unsigned_rpms_empty_input():
    rpms_to_check = defaultdict(list)

    third_party_rpms, third_party_files = scanthirdpartytargetpythonmodules.identify_unsigned_rpms(rpms_to_check)

    assert len(third_party_rpms) == 0
    assert len(third_party_files) == 0
