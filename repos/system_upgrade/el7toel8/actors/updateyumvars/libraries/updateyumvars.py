import os

from leapp.libraries.stdlib import api

VAR_FOLDERS = ["/etc/yum/vars", "/etc/dnf/vars/"]


def vars_update():
    """ Iterate through and modify the variables. """
    for var_folder in VAR_FOLDERS:
        if not os.path.isdir(var_folder):
            api.current_logger().debug(
                "The {} directory doesn't exist. Skipping to next.".format(var_folder)
            )
            continue

        for varfile_name in os.listdir(var_folder):
            # cp_centos_major_version contains the current OS' major version.
            if varfile_name == 'cp_centos_major_version':
                varfile_path = os.path.join(var_folder, varfile_name)

                with open(varfile_path, 'w') as varfile:
                    # Overwrite the value from outdated "7".
                    varfile.write('8')
