"""
Start and stop platform services to boot and shut down a Shasta system.

(C) Copyright 2021 Hewlett Packard Enterprise Development LP.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
"""

from collections import namedtuple
import logging
import socket
from paramiko import SSHClient, SSHException, WarningPolicy
from threading import Thread

from sat.cli.bootsys.ceph import ceph_healthy, freeze_ceph
from sat.cli.bootsys.util import get_mgmt_ncn_hostnames
from sat.cli.bootsys.waiting import Waiter
from sat.util import pester_choices

LOGGER = logging.getLogger(__name__)

# Get a list of containers using crictl ps. With a 5 minute overall timeout, run up to 50 'crictl ps' commands at
# a time with up to 3 containers per command. Each 'crictl stop' command has a timeout of 5 seconds per container,
# adding up to 15 seconds if they all time out.
CONTAINER_STOP_SCRIPT = (
    'crictl ps -q | '
    'timeout -s 9 5m xargs -n 3 -P 50 '
    'timeout -s 9 --foreground 15s crictl stop --timeout 5'
)
# Default timeout in seconds for service start/stop actions
SERVICE_ACTION_TIMEOUT = 30


class FatalPlatformError(Exception):
    """A fatal error occurred during the shutdown or startup of platform services."""
    pass


class RemoteServiceWaiter(Waiter):
    """Start/stop and optionally enable/disable a service over SSH and wait for it to reach target state."""

    VALID_TARGET_STATE_VALUES = ('active', 'inactive')
    VALID_TARGET_ENABLED_VALUES = ('enabled', 'disabled')

    def __init__(self, host, service_name, target_state, timeout, poll_interval=5, target_enabled=None):
        """Construct a new RemoteServiceWaiter.

        Args:
            host (str): the hostname on which to operate.
            service_name (str): the name of the service on the remote host.
            target_state (str): the desired state of the service, e.g.
                'active' or 'inactive'
            timeout (int): the timeout, in seconds, for the wait operation.
            poll_interval (int): the interval, in seconds, between polls for
                completion.
            target_enabled (str or None): If 'enabled', enable the service.
                If 'disabled', disable the service. If None, do neither.
        """
        super().__init__(timeout, poll_interval=poll_interval)

        # Validate input
        if target_state not in self.VALID_TARGET_STATE_VALUES:
            raise ValueError(f'Invalid target state {target_state}. '
                             f'Must be one of {self.VALID_TARGET_STATE_VALUES}')
        if target_enabled is not None and target_enabled not in self.VALID_TARGET_ENABLED_VALUES:
            raise ValueError(f'Invalid target enabled {target_enabled}. '
                             f'Must be one of {self.VALID_TARGET_ENABLED_VALUES}')

        self.host = host
        self.service_name = service_name
        self.target_state = target_state
        self.target_enabled = target_enabled
        self.ssh_client = SSHClient()

    def _run_remote_command(self, command, nonzero_error=True):
        """Run the given command on the remote host.

        Args:
            command (str): The command to run on the remote host.
            nonzero_error (bool): If true, raise a RuntimeError for
                non-zero exit codes.

        Returns:
            A 2-tuple of paramiko.channel.ChannelFile objects representing
            stdout and stderr from the command.

        Raises:
            RuntimeError: if the command returned a non-zero exit code
                and nonzero_exit = True.
            SSHException: if the server failed to execute the command.
        """
        LOGGER.debug('Executing command "%s" on host %s', command, self.host)
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code and nonzero_error:
            error_message = (f'Command {command} on host {self.host} returned non-zero exit code {exit_code}. '
                             f'Stdout: "{stdout.read()}" Stderr: "{stderr.read()}"')
            raise RuntimeError(error_message)

        return stdout, stderr

    def wait_for_completion(self):
        """Wait for completion but catch and log errors, and fail if errors are caught."""
        try:
            return super().wait_for_completion()
        except (RuntimeError, socket.error, SSHException) as e:
            LOGGER.error(e)
            return False

    def condition_name(self):
        return (f'service {self.service_name} {self.target_state} '
                f'{f"and {self.target_enabled} " if self.target_enabled else ""}'
                f'on {self.host}')

    def pre_wait_action(self):
        """Connect to remote host and start/stop the service if needed.

        This method will set `self.completed` to True if no action is needed.

        Raises:
            SSHException, socket.error: if connecting to the host fails,
                or if the server failed to execute a command.
            RuntimeError, SSHException: from _run_remote_command.
        """
        systemctl_action = ('stop', 'start')[self.target_state == 'active']
        self.ssh_client.load_system_host_keys()
        self.ssh_client.set_missing_host_key_policy(WarningPolicy)
        self.ssh_client.connect(self.host)
        if self.has_completed():
            self.completed = True
        else:
            LOGGER.debug('Found service not in %s state on host %s.', self.target_state, self.host)
            self._run_remote_command(f'systemctl {systemctl_action} {self.service_name}')

        if self.target_enabled and self._get_enabled() != self.target_enabled:
            LOGGER.debug('Found service not in %s state on host %s.', self.target_enabled, self.host)
            systemctl_action = ('disable', 'enable')[self.target_enabled == 'enabled']
            self._run_remote_command(f'systemctl {systemctl_action} {self.service_name}')

    def _get_active(self):
        """Check whether the service is active or not according to systemctl.

        Returns:
            The string representation of the service's state; e.g.
                'active', 'inactive' or 'unknown'.

        Raises:
            RuntimeError, SSHException: from _run_remote_command.
        """
        # systemctl is-active always exits with a non-zero code if the service is not active
        stdout, stderr = self._run_remote_command(f'systemctl is-active {self.service_name}',
                                                  nonzero_error=False)
        return stdout.read().decode().strip()

    def _get_enabled(self):
        """Check whether the service is enabled or not according to systemctl.

        Returns:
            The string representation of the service's enabled status; e.g.
                'enabled', 'disabled', or 'unknown'.

        Raises:
            RuntimeError, SSHException: from _run_remote_command.
        """
        # systemctl is-enabled always exits with a non-zero code if the service is not active
        stdout, stderr = self._run_remote_command(f'systemctl is-enabled {self.service_name}',
                                                  nonzero_error=False)
        return stdout.read().decode().strip()

    def has_completed(self):
        """Check that the service is active or inactive on the remote host.

        Raises:
            RuntimeError, SSHException: from _get_active.
        """
        current_state = self._get_active()
        return current_state == self.target_state


def prompt_for_ncn_verification():
    """Get NCNs by group and prompt user for confirmation of correctness.

    Returns:
        A dictionary mapping from NCN group name to sorted lists of nodes in group.

    Raises:
        FatalPlatformError: if admin answers prompt by saying NCN groups are
            incorrect.
    """
    ncns_by_group = {
        'managers': sorted(get_mgmt_ncn_hostnames(['managers'])),
        'workers': sorted(get_mgmt_ncn_hostnames(['workers'])),
        'kubernetes': sorted(get_mgmt_ncn_hostnames(['managers', 'workers']))
    }

    print('Identified the following Non-compute Node (NCN) groups as follows.')
    for name, members in ncns_by_group.items():
        print(f'{name}: {members}')

    empty_groups = [name for name, members in ncns_by_group.items()
                    if not members]
    if empty_groups:
        raise FatalPlatformError(f'Failed to identify members of the following '
                                 f'NCN group(s): {empty_groups}')

    if pester_choices('Are the above NCN groupings correct?', ('yes', 'no')) == 'no':
        raise FatalPlatformError('User indicated NCN groups are incorrect.')

    return ncns_by_group


def stop_containers(host):
    """Stop containers running on a host under containerd using crictl.

    Args:
        host (str): The hostname of the node on which the containers should be
            stopped.

    Returns:
        None

    Raises:
        SystemExit: if connecting to the host failed or if the command exited
            with a non-zero code.
    """
    # Raises SSHException or socket.error
    try:
        ssh_client = SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(WarningPolicy)
        ssh_client.connect(host)
    except (socket.error, SSHException) as e:
        LOGGER.error(f'Failed to connect to host {host}: {e}')
        raise SystemExit(1)

    stdin, stdout, stderr = ssh_client.exec_command(CONTAINER_STOP_SCRIPT)
    if stdout.channel.recv_exit_status():
        LOGGER.warning(
            f'Stopping containerd containers on host {host} return non-zero exit status. '
            f'Stdout:"{stdout.read()}". Stderr:"{stderr.read()}".'
        )


def do_service_action_on_hosts(hosts, service, target_state,
                               timeout=SERVICE_ACTION_TIMEOUT, target_enabled=None):
    """Do a service start/stop and optionally enable/disable across hosts in parallel.

    Args:
        hosts (list of str): The list of hosts on which to operate.
        service (str): The name of the service on which to operate.
        target_state (str): The desired active/inactive state of the service
        timeout (int): The timeout of the service operation on each host.
        target_enabled (str or None): The desired enabled/disabled state of the
            service or None if not applicable.

    Returns:
        None

    Raises:
        FatalPlatformError: if the service action fails on any of the given hosts
    """
    service_action_waiters = [RemoteServiceWaiter(host, service, target_state=target_state,
                                                  timeout=timeout, target_enabled=target_enabled)
                              for host in hosts]
    for waiter in service_action_waiters:
        waiter.wait_for_completion_async()
    for waiter in service_action_waiters:
        waiter.wait_for_completion_await()

    if not all(waiter.completed for waiter in service_action_waiters):
        raise FatalPlatformError(f'Failed to ensure {service} is {target_state} '
                                 f'{f"and {target_enabled} " if target_enabled else ""}'
                                 f'on all hosts.')


def do_containerd_stop(ncn_groups):
    """Stop containers in containerd and stop containerd itself on all K8s NCNs.

    Raises:
        FatalPlatformError: if any nodes fail to stop containerd
    """
    k8s_ncns = ncn_groups['kubernetes']
    # This currently stops all containers in parallel before stopping containerd
    # on each ncn in parallel.  It probably could be faster if it was all in parallel.
    container_stop_threads = [Thread(target=stop_containers, args=(ncn,)) for ncn in k8s_ncns]
    for thread in container_stop_threads:
        thread.start()
    for thread in container_stop_threads:
        thread.join()

    do_service_action_on_hosts(k8s_ncns, 'containerd', target_state='inactive')


def do_containerd_start(ncn_groups):
    """Start and enable containerd on all K8s NCNs.

    Raises:
        FatalPlatformError: if any nodes fail to start containerd
    """
    do_service_action_on_hosts(ncn_groups['kubernetes'], 'containerd',
                               target_state='active', target_enabled='enabled')


def do_kubelet_stop(ncn_groups):
    """Stop and disable kubelet on all K8s NCNs.

    Raises:
        FatalPlatformError: if any nodes fail to stop kubelet
    """
    do_service_action_on_hosts(ncn_groups['kubernetes'], 'kubelet',
                               target_state='inactive', target_enabled='disabled')


def do_kubelet_start(ncn_groups):
    """Start and enable kubelet on all K8s NCNs.

    Raises:
        FatalPlatformError: if any nodes fail to start kubelet.
    """
    do_service_action_on_hosts(ncn_groups['kubernetes'], 'kubelet',
                               target_state='active', target_enabled='enabled')


def do_ceph_freeze(ncn_groups):
    """Check ceph health and freeze if healthy.

    Raises:
        FatalPlatformError: if ceph is not healthy or if freezing ceph fails.
    """
    if not ceph_healthy():
        raise FatalPlatformError('Ceph is not healthy. Please correct Ceph health and try again.')
    try:
        freeze_ceph()
    except RuntimeError as err:
        raise FatalPlatformError(str(err))


# Each step has a description that is printed and an action that is called
# with the single argument being a dict mapping from NCN group names to hosts.
PlatformServicesStep = namedtuple('PlatformServicesStep', ('description', 'action'))
STEPS_BY_ACTION = {
    # The ordered steps to start platform services
    'start': [
        PlatformServicesStep('Start containerd on all Kubernetes NCNs.', do_containerd_start),
        PlatformServicesStep('Start and enable kubelet on all Kubernetes NCNs.', do_kubelet_start)
    ],
    # The ordered steps to stop platform services
    'stop': [
        PlatformServicesStep('Stop and disable kubelet on all Kubernetes NCNs.', do_kubelet_stop),
        PlatformServicesStep('Stop containers running under containerd and stop containerd '
                             'on all Kubernetes NCNs.',
                             do_containerd_stop),
        PlatformServicesStep('Check health of Ceph cluster and freeze state.', do_ceph_freeze)
    ]
}


def do_platform_action(action):
    """Do a platform action with the given ordered steps.

    Args:
        action (str): The action to take. Must be a key in STEPS_BY_ACTION.

    Returns:
        None

    Raises:
        SystemExit: if given an unknown action or the action encounters a fatal error.
    """
    try:
        steps = STEPS_BY_ACTION[action]
    except KeyError:
        LOGGER.error(f'Invalid action "{action}" to perform on platform services.')
        raise SystemExit(1)

    try:
        ncn_groups = prompt_for_ncn_verification()
    except FatalPlatformError as err:
        LOGGER.error(f'Not proceeding with platform {action}: {err}')
        raise SystemExit(1)

    for step in steps:
        try:
            info_message = f'Executing step: {step.description}'
            print(info_message)
            LOGGER.info(info_message)
            step.action(ncn_groups)
        except FatalPlatformError as err:
            LOGGER.error(f'Fatal error while stopping platform services during '
                         f'step "{step.description}": {err}')
            raise SystemExit(1)


def do_platform_stop(args):
    """Stop services to shut down a Shasta system.

    Args:
        args: The argparse.Namespace object containing the parsed arguments
            passed to this stage.

    Returns:
        None
    """
    do_platform_action('stop')


def do_platform_start(args):
    """Start services to boot a Shasta system.

    Args:
        args: The argparse.Namespace object containing the parsed arguments
            passed to this stage.
    """
    do_platform_action('start')
