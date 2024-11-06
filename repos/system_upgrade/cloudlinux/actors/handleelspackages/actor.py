import os

from leapp.actors import Actor
from leapp.libraries.common.cllaunch import run_on_cloudlinux
from leapp.libraries.stdlib import run
from leapp.tags import DownloadPhaseTag, IPUWorkflowTag


class HandleElsPackages(Actor):
    name = "handle_els_packages"
    consumes = ()
    produces = ()
    tags = (DownloadPhaseTag.Before, IPUWorkflowTag)

    @run_on_cloudlinux
    def process(self):
        try:
            script_path = self.get_file_path("els_script_handler.sh")
            os.chmod(script_path, 0o755)
            result = run([script_path])
            if result["exit_code"] != 0:
                self.log.error(
                    "Cleanup script failed with exit code: %d\nError: %s",
                    result["exit_code"],
                    result["stderr"],
                )
            else:
                self.log.info("Cleanup script executed successfully")
        except Exception as e:
            self.log.error("Failed to execute cleanup script: %s", str(e))
