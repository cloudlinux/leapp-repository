import os
import errno
import shutil

from leapp.actors import Actor
from leapp.models import InstalledRPM
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag
from leapp.libraries.common.cllaunch import run_on_cloudlinux


class ClearPackageConflicts(Actor):
    """
    Remove several python package files manually to resolve conflicts between versions of packages to be upgraded.
    """

    name = "clear_package_conflicts"
    consumes = (InstalledRPM,)
    produces = ()
    tags = (DownloadPhaseTag.Before, IPUWorkflowTag)
    rpm_lookup = None

    def has_package(self, name):
        """
        Check whether the package is installed.
        Looks only for the package name, nothing else.
        """
        if self.rpm_lookup:
            return name in self.rpm_lookup

    def problem_packages_installed(self, problem_packages):
        """
        Check whether any of the problem packages are present in the system.
        """
        for pkg in problem_packages:
            if self.has_package(pkg):
                self.log.debug("Conflicting package {} detected".format(pkg))
                return True
        return False

    def clear_problem_files(self, problem_files, problem_dirs):
        """
        Go over the list of problem files and directories and remove them if they exist.
        They'll be replaced by the new packages.
        """
        for p_dir in problem_dirs:
            try:
                if os.path.isdir(p_dir):
                    shutil.rmtree(p_dir)
                    self.log.debug("Conflicting directory {} removed".format(p_dir))
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

        for p_file in problem_files:
            try:
                if os.path.isfile(p_file):
                    os.remove(p_file)
                    self.log.debug("Conflicting file {} removed".format(p_file))
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

    def alt_python37_handle(self):
        """
        These alt-python37 packages are conflicting with their own builds for EL8.
        """
        problem_packages = [
            "alt-python37-six",
            "alt-python37-pytz",
        ]
        problem_files = []
        problem_dirs = [
            "/opt/alt/python37/lib/python3.7/site-packages/six-1.15.0-py3.7.egg-info",
            "/opt/alt/python37/lib/python3.7/site-packages/pytz-2017.2-py3.7.egg-info",
        ]

        if self.problem_packages_installed(problem_packages):
            self.clear_problem_files(problem_files, problem_dirs)

    def lua_cjson_handle(self):
        """
        lua-cjson package is conflicting with the incoming lua-cjson package for EL8.
        """
        problem_packages = [
            "lua-cjson"
        ]
        problem_files = [
            "/usr/lib64/lua/5.1/cjson.so",
            "/usr/share/lua/5.1/cjson/tests/bench.lua",
            "/usr/share/lua/5.1/cjson/tests/genutf8.pl",
            "/usr/share/lua/5.1/cjson/tests/test.lua",
        ]
        problem_dirs = []

        if self.problem_packages_installed(problem_packages):
            self.clear_problem_files(problem_files, problem_dirs)

    @run_on_cloudlinux
    def process(self):
        # todo: (CLOS-3205) investigate why set is needed here
        self.rpm_lookup = [rpm for rpm in self.consume(InstalledRPM)]
        self.alt_python37_handle()
