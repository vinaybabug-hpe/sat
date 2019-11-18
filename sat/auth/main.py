"""
Entry point for the auth subcommand.

Copyright 2019 Cray Inc. All Rights Reserved.
"""

import getpass
import logging

from sat.config import get_config_value
from sat.session import SATSession

LOGGER = logging.getLogger(__name__)


def do_auth(args):
    """Prompts user for a password, fetches a token, and saves it to disk.

    The prompt indicates the username to be used in combination with the
    password. The command-line argument "--username" is checked first, then
    the "username" option in the configuration file, and if nothing is found,
    getpass.getuser() is called to get the system username of the user invoking sat.

    The token is saved to $HOME/.config/sat/tokens/hostname.username.json,
    unless overriden by --token-file on the command line.

    Args:
        args: The argparse.Namespace object containing the parsed arguments
            passed to this subcommand.

    Returns:
        None
    """

    session = SATSession(no_unauth_warn=True)
    password = getpass.getpass('Password for {}: '.format(session.username))

    session.fetch_token(password)
    if session.token:
        print('Succeeded!')
        session.save()
    else:
        print('Authenication failed!')
        LOGGER.error('Authentication Failed.')
        raise SystemExit(1)
