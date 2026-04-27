import os

try:
    # py2
    import ConfigParser as configparser
    ParserClass = configparser.SafeConfigParser
except ImportError:
    # py3
    import configparser
    ParserClass = configparser.ConfigParser


# DNF plugin config path on the target system (CL8). FirstBoot runs after the
# target OS is already in place; on CL8 the plugin package is
# dnf-plugin-spacewalk (PES replacement for CL7's yum-rhn-plugin,
# pes-events id=1586) and its config ships with enabled=0.
DEFAULT_CONFIG_PATH = '/etc/dnf/plugins/spacewalk.conf'


def _enable_plugin(config_path, parser_cls=ParserClass, log=None):
    """Enable the DNF spacewalk plugin at `config_path`.

    Returns `(changed, title)` where `title` is `None` on success or
    when the plugin is not installed, and otherwise a human-readable
    problem description suitable for a Leapp report.

    Absence of `config_path` is treated as a silent skip: on no-auth /
    SWNG systems (CLOS-4056) `rhn-client-tools >= 3.0.1` Obsoletes the
    `dnf-plugin-spacewalk` package, so the config file is either gone by
    then, or doesn't do anything.
    """
    if not os.path.exists(config_path):
        return False, None
    parser = parser_cls(allow_no_value=True)
    try:
        parser.read(config_path)
        if parser.get('main', 'enabled') != '1':
            parser.set('main', 'enabled', '1')
            with open(config_path, 'w') as f:
                parser.write(f)
            if log is not None:
                log.info('DNF spacewalk plugin enabled')
            return True, None
        return False, None
    except Exception as e:
        return False, 'DNF spacewalk plugin config error: %s' % e
