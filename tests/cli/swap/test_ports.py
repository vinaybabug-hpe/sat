#
# MIT License
#
# (C) Copyright 2020-2021, 2024 Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
"""
Unit tests for sat.cli.swap.ports
"""

import logging
import os
import unittest
from unittest import mock
from unittest.mock import call

from sat.cli.swap.ports import PortManager
from tests.common import ExtendedTestCase


# Constants used in the tests
EDGE_POLICY_LINK = '/fabric/port-policies/edge-policy'
FABRIC_POLICY_LINK = '/fabric/port-policies/fabric-policy'
QOS_POLICY_LINK = '/fabric/port-policies/qos-ll_be_bd_et-fabric-policy'


class TestGetSwitchPortDataList(unittest.TestCase):
    """Unit test for Switch get_switch_port_data_list()."""

    def setUp(self):
        """Mock functions called."""

        # A switch with only an edge port
        self.edge_switch = 'x1000c6r7'
        # A lone edge port on a switch and the data returned by get_port on it
        self.lone_edge_port = f'{self.edge_switch}j100p0'
        self.lone_edge_port_link = f'/fabric/ports/{self.lone_edge_port}'
        self.lone_edge_port_data = {
            'conn_port': self.lone_edge_port,
            'portPolicyLinks': [EDGE_POLICY_LINK]
        }

        # A switch with only a fabric port
        self.fabric_switch = 'x1000c1r3'
        # A lone fabric port on a switch and the data returned by get_port on it
        self.lone_fabric_port = f'{self.fabric_switch}j20p1'
        self.lone_fabric_port_link = f'/fabric/ports/{self.lone_fabric_port}'
        self.lone_fabric_port_data = {
            'conn_port': self.lone_fabric_port,
            'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]
        }

        # A switch with both fabric and edge ports
        self.fabric_edge_switch = 'x1000c0r1'
        self.fabric_port_1 = f'{self.fabric_edge_switch}j100p0'
        self.fabric_port_1_link = f'/fabric/ports/{self.fabric_port_1}'
        self.fabric_port_1_data = {
            'conn_port': self.fabric_port_1,
            'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]
        }
        self.fabric_port_2 = f'{self.fabric_edge_switch}j100p1'
        self.fabric_port_2_link = f'/fabric/ports/{self.fabric_port_2}'
        self.fabric_port_2_data = {
            'conn_port': self.fabric_port_2,
            'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]
        }
        self.edge_port = f'{self.fabric_edge_switch}j20p0'
        self.edge_port_link = f'/fabric/ports/{self.edge_port}'
        self.edge_port_data = {
            'conn_port': self.edge_port,
            'portPolicyLinks': [EDGE_POLICY_LINK]
        }

        self.mock_ports = {
            self.lone_edge_port_link: self.lone_edge_port_data,
            self.lone_fabric_port_link: self.lone_fabric_port_data,
            self.fabric_port_1_link: self.fabric_port_1_data,
            self.fabric_port_2_link: self.fabric_port_2_data,
            self.edge_port_link: self.edge_port_data
        }

        self.mock_get_port = mock.patch('sat.cli.swap.ports.PortManager.get_port',
                                        autospec=True).start()
        self.mock_get_port.side_effect = lambda _, port_xname: self.mock_ports.get(port_xname)

        self.mock_get_switches = mock.patch('sat.cli.swap.ports.PortManager.get_switches',
                                            autospec=True).start()
        self.mock_get_switches.return_value = [
            f'/fabric/switches/{self.edge_switch}b0',
            f'/fabric/switches/{self.fabric_switch}b0',
            f'/fabric/switches/{self.fabric_edge_switch}b0'
        ]

        self.mock_switches = {
            # Example switch with just an edge port
            f'/fabric/switches/{self.edge_switch}b0': {
                'edgePortLinks': [self.lone_edge_port_link],
                'fabricPortLinks': []
            },
            # Example switch with just fabric ports
            f'/fabric/switches/{self.fabric_switch}b0': {
                'edgePortLinks': [],
                'fabricPortLinks': [self.lone_fabric_port_link]
            },
            # Example switch with fabric and edge ports
            f'/fabric/switches/{self.fabric_edge_switch}b0': {
                'edgePortLinks': [self.edge_port_link],
                'fabricPortLinks': [self.fabric_port_1_link, self.fabric_port_2_link]
            }
        }
        self.mock_get_switch = mock.patch('sat.cli.swap.ports.PortManager.get_switch',
                                          autospec=True).start()
        self.mock_sat_session = mock.patch('sat.cli.swap.ports.SATSession').start()
        self.mock_get_switch.side_effect = lambda _, switch_xname: self.mock_switches.get(switch_xname)
        self.pm = PortManager()

    def test_switch_edge_ports_only(self):
        """Test get_switch_port_data_list with a switch that only has edge ports"""
        # It should work with or without the 'b0' on the end of the switch xname
        for switch_xname in [self.edge_switch, f'{self.edge_switch}b0']:
            result = self.pm.get_switch_port_data_list(switch_xname)
            expected = [{'xname': 'x1000c6r7j100p0',
                         'port_link': self.lone_edge_port_link,
                         'policy_links': [EDGE_POLICY_LINK]}]
            self.assertEqual(result, expected)

    def test_switch_fabric_ports_only(self):
        """Test get_switch_port_data_list with a switch that only has fabric ports"""
        # It should work with or without the 'b0' on the end of the switch xname
        for switch_xname in [self.fabric_switch, f'{self.fabric_switch}b0']:
            result = self.pm.get_switch_port_data_list(switch_xname)
            expected = [{'xname': self.lone_fabric_port,
                         'port_link': self.lone_fabric_port_link,
                         'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]}]
            self.assertEqual(result, expected)

    def test_switch_fabric_and_edge_ports(self):
        """Test get_switch_port_data_list with a switch with fabric and edge ports"""
        # It should work with or without the 'b0' on the end of the switch xname
        for switch_xname in [self.fabric_edge_switch, f'{self.fabric_edge_switch}b0']:
            result = self.pm.get_switch_port_data_list(switch_xname)
            expected = [
                {'xname': self.fabric_port_1,
                 'port_link': self.fabric_port_1_link,
                 'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
                {'xname': self.fabric_port_2,
                 'port_link': self.fabric_port_2_link,
                 'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
                {'xname': self.edge_port,
                 'port_link': self.edge_port_link,
                 'policy_links': [EDGE_POLICY_LINK]}
            ]
            self.assertCountEqual(result, expected)

    def tearDown(self):
        mock.patch.stopall()


class TestGetJackPortDataList(unittest.TestCase):
    """Unit test for cable get_jack_port_data_list()."""

    def setUp(self):
        """Mock functions called."""

        self.mock_sat_session = mock.patch('sat.cli.swap.ports.SATSession').start()
        self.mock_fc_client = mock.patch('sat.cli.swap.ports.FabricControllerClient').start().return_value
        # The data that will be returned for the ports
        # Each call for the mock_fc_client will return an item from the list in order
        # Example URL: https://api-gw-service-nmn.local/apis/fabric-manager/fabric/ports/x9000c1r3j16p0
        self.mock_fc_client.get.return_value.json.side_effect = [
            {'id': 'x9000c1r3a0l14',
             'conn_port': 'x9000c1r3j16p0',
             'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'id': 'x9000c1r3a0l14',
             'conn_port': 'x9000c1r3j16p1',
             'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'id': 'x9000c3r3a2l13',
             'conn_port': 'x9000c3r5j16p0',
             'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'id': 'x9000c3r3a0214',
             'conn_port': 'x9000c3r5j16p1',
             'portPolicyLinks': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
        ]

        self.mock_cable_endpoints = mock.patch('sat.cli.swap.ports.CableEndpoints',
                                               autospec=True).start().return_value
        self.mock_cable_endpoints.get_cable.side_effect = {
            'src_conn_a': 'x9000c1r3j16',
            'src_conn_b': 'none',
            'dst_conn_a': 'x9000c3r5j16',
            'dst_conn_b': 'none'
        }
        self.mock_cable_endpoints.get_linked_jack_list.side_effect = [
            ['x9000c1r3j16',
             'x9000c3r5j16']
        ]

        self.mock_get_ports = mock.patch('sat.cli.swap.ports.PortManager.get_ports',
                                         autospec=True).start()
        self.mock_get_ports.return_value = [
            '/fabric/ports/x9000c1r3j16p0',
            '/fabric/ports/x9000c1r3j16p1',
            '/fabric/ports/x9000c3r5j16p0',
            '/fabric/ports/x9000c3r5j16p1',
            '/fabric/ports/x9000c1r3j18p0',
            '/fabric/ports/x9000c1r3j18p1',
            '/fabric/ports/x9000c3r3j16p0',
            '/fabric/ports/x9000c3r3j16p1'
        ]

        self.success_expected = [
            {'xname': 'x9000c1r3j16p0',
             'port_link': '/fabric/ports/x9000c1r3j16p0',
             'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'xname': 'x9000c1r3j16p1',
             'port_link': '/fabric/ports/x9000c1r3j16p1',
             'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'xname': 'x9000c3r5j16p0',
             'port_link': '/fabric/ports/x9000c3r5j16p0',
             'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'xname': 'x9000c3r5j16p1',
             'port_link': '/fabric/ports/x9000c3r5j16p1',
             'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]}
        ]

        self.mock_cable_endpoints.load_cables_from_p2p_file.return_value = True
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.return_value = True
        self.maxDiff = None
        self.pm = PortManager()

    def test_basic(self):
        """get_jack_port_data_list() with a single jack returns the endpoint data for the jacks"""

        result = self.pm.get_jack_port_data_list(['x9000c1r3j16'])
        self.assertEqual(result, self.success_expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_called()
        self.mock_cable_endpoints.get_cable.assert_called()
        self.mock_cable_endpoints.get_linked_jack_list.assert_called()
        self.mock_get_ports.assert_called()
        self.mock_fc_client.get.assert_has_calls(
            [call('/fabric/ports/x9000c1r3j16p0'), call().json(),
             call('/fabric/ports/x9000c1r3j16p1'), call().json(),
             call('/fabric/ports/x9000c3r5j16p0'), call().json(),
             call('/fabric/ports/x9000c3r5j16p1'), call().json()]
        )

    def test_both_jacks(self):
        """get_jack_port_data_list() with jacks connected by a cable returns the endpoint data for the jacks"""

        self.mock_cable_endpoints.get_cable.side_effect = [
            {'src_conn_a': 'x9000c1r3j16',
             'src_conn_b': 'none',
             'dst_conn_a': 'x9000c3r5j16',
             'dst_conn_b': 'none'},
            {'src_conn_a': 'x9000c1r3j16',
             'src_conn_b': 'none',
             'dst_conn_a': 'x9000c3r5j16',
             'dst_conn_b': 'none'}
        ]
        self.mock_cable_endpoints.get_linked_jack_list.side_effect = [
            ['x9000c1r3j16',
             'x9000c3r5j16'],
            ['x9000c1r3j16',
             'x9000c3r5j16']
        ]
        result = self.pm.get_jack_port_data_list(['x9000c1r3j16', 'x9000c3r5j16'])
        self.assertEqual(result, self.success_expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_called()
        self.assertEqual(self.mock_cable_endpoints.get_cable.call_count, 2)
        self.assertEqual(self.mock_cable_endpoints.get_linked_jack_list.call_count, 2)
        self.mock_get_ports.assert_called()
        self.mock_fc_client.get.assert_has_calls(
            [call('/fabric/ports/x9000c1r3j16p0'), call().json(),
             call('/fabric/ports/x9000c1r3j16p1'), call().json(),
             call('/fabric/ports/x9000c3r5j16p0'), call().json(),
             call('/fabric/ports/x9000c3r5j16p1'), call().json()]
        )

    def test_invalid_jack_xname(self):
        """get_jack_port_data_list() with an invalid xname"""

        expected = None
        result = self.pm.get_jack_port_data_list(['x9000c1r3'])
        self.assertEqual(result, expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_not_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_not_called()
        self.mock_cable_endpoints.get_cable.assert_not_called()
        self.mock_cable_endpoints.get_linked_jack_list.assert_not_called()
        self.mock_get_ports.assert_not_called()

    def test_no_p2p_file(self):
        """get_jack_port_data_list() with no p2p file"""

        self.mock_cable_endpoints.load_cables_from_p2p_file.return_value = False
        expected = None
        result = self.pm.get_jack_port_data_list(['x9000c1r3j16'])
        self.assertEqual(result, expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_not_called()
        self.mock_cable_endpoints.get_cable.assert_not_called()
        self.mock_cable_endpoints.get_linked_jack_list.assert_not_called()
        self.mock_get_ports.assert_not_called()

    def test_no_p2p_file_with_force(self):
        """get_jack_port_data_list() with no p2p file with force"""

        self.mock_cable_endpoints.load_cables_from_p2p_file.return_value = False
        expected = [
            {'xname': 'x9000c1r3j16p0',
             'port_link': '/fabric/ports/x9000c1r3j16p0',
             'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]},
            {'xname': 'x9000c1r3j16p1',
             'port_link': '/fabric/ports/x9000c1r3j16p1',
             'policy_links': [FABRIC_POLICY_LINK, QOS_POLICY_LINK]}
        ]
        result = self.pm.get_jack_port_data_list(['x9000c1r3j16'], force=True)
        self.assertEqual(result, expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_not_called()
        self.mock_cable_endpoints.get_cable.assert_not_called()
        self.mock_cable_endpoints.get_linked_jack_list.assert_not_called()
        self.mock_get_ports.assert_called()
        self.mock_fc_client.get.assert_has_calls(
            [call('/fabric/ports/x9000c1r3j16p0'), call().json(),
             call('/fabric/ports/x9000c1r3j16p1'), call().json()]
        )

    def test_jack_not_valid_using_p2p_file(self):
        """get_jack_port_data_list() with jack not valid using p2p file"""

        self.mock_cable_endpoints.validate_jacks_using_p2p_file.return_value = False
        expected = None
        result = self.pm.get_jack_port_data_list(['x9000c1r3j16'])
        self.assertEqual(result, expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_called()
        self.mock_cable_endpoints.get_cable.assert_not_called()
        self.mock_cable_endpoints.get_linked_jack_list.assert_not_called()
        self.mock_get_ports.assert_not_called()

    def test_jack_not_valid_using_p2p_file_with_force(self):
        """get_jack_port_data_list() with jack not valid using p2p file with force"""

        self.mock_cable_endpoints.validate_jacks_using_p2p_file.return_value = False
        result = self.pm.get_jack_port_data_list(['x9000c1r3j16'], force=True)
        self.assertEqual(result, self.success_expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_called()
        self.assertEqual(self.mock_cable_endpoints.get_cable.call_count, 1)
        self.assertEqual(self.mock_cable_endpoints.get_linked_jack_list.call_count, 1)
        self.mock_get_ports.assert_called()
        self.mock_fc_client.get.assert_has_calls(
            [call('/fabric/ports/x9000c1r3j16p0'), call().json(),
             call('/fabric/ports/x9000c1r3j16p1'), call().json(),
             call('/fabric/ports/x9000c3r5j16p0'), call().json(),
             call('/fabric/ports/x9000c3r5j16p1'), call().json()]
        )

    def test_jacks_two_cables_with_force(self):
        """get_jack_port_data_list() with jacks for two separate cables with force"""

        self.mock_cable_endpoints.validate_jacks_using_p2p_file.return_value = False
        self.mock_cable_endpoints.get_cable.side_effect = [
            {'src_conn_a': 'x9000c1r3j16',
             'src_conn_b': 'none',
             'dst_conn_a': 'x9000c3r5j16',
             'dst_conn_b': 'none'},
            {'src_conn_a': 'x9000c1r3j18',
             'src_conn_b': 'none',
             'dst_conn_a': 'x9000c3r3j16',
             'dst_conn_b': 'none'}
        ]
        self.mock_cable_endpoints.get_linked_jack_list.side_effect = [
            ['x9000c1r3j16',
             'x9000c3r5j16'],
            ['x9000c1r3j18',
             'x9000c3r3j16']
        ]
        self.mock_fc_client.get.return_value.json.side_effect = [
            {'id': 'x9000c1r3a0l14',
             'conn_port': 'x9000c1r3j16p0',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c1r3a0l15',
             'conn_port': 'x9000c1r3j16p1',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c1r3a0l16',
             'conn_port': 'x9000c1r3j18p0',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c1r3a0l17',
             'conn_port': 'x9000c1r3j18p1',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c3r3a2l18',
             'conn_port': 'x9000c3r3j16p0',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c3r3a0219',
             'conn_port': 'x9000c3r3j16p1',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c3r3a2l13',
             'conn_port': 'x9000c3r5j16p0',
             'portPolicyLinks': [FABRIC_POLICY_LINK]},
            {'id': 'x9000c3r3a0214',
             'conn_port': 'x9000c3r5j16p1',
             'portPolicyLinks': [FABRIC_POLICY_LINK]}
        ]
        expected = [
            {'xname': 'x9000c1r3j16p0',
             'port_link': '/fabric/ports/x9000c1r3j16p0',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c1r3j16p1',
             'port_link': '/fabric/ports/x9000c1r3j16p1',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c1r3j18p0',
             'port_link': '/fabric/ports/x9000c1r3j18p0',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c1r3j18p1',
             'port_link': '/fabric/ports/x9000c1r3j18p1',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c3r3j16p0',
             'port_link': '/fabric/ports/x9000c3r3j16p0',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c3r3j16p1',
             'port_link': '/fabric/ports/x9000c3r3j16p1',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c3r5j16p0',
             'port_link': '/fabric/ports/x9000c3r5j16p0',
             'policy_links': [FABRIC_POLICY_LINK]},
            {'xname': 'x9000c3r5j16p1',
             'port_link': '/fabric/ports/x9000c3r5j16p1',
             'policy_links': [FABRIC_POLICY_LINK]}
        ]
        result = self.pm.get_jack_port_data_list(['x9000c1r3j16', 'x9000c1r3j18'], force=True)
        self.assertEqual(result, expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_called()
        self.assertEqual(self.mock_cable_endpoints.get_cable.call_count, 2)
        self.assertEqual(self.mock_cable_endpoints.get_linked_jack_list.call_count, 2)
        self.mock_get_ports.assert_called()
        self.mock_fc_client.get.assert_has_calls(
            [call('/fabric/ports/x9000c1r3j16p0'), call().json(),
             call('/fabric/ports/x9000c1r3j16p1'), call().json(),
             call('/fabric/ports/x9000c1r3j18p0'), call().json(),
             call('/fabric/ports/x9000c1r3j18p1'), call().json(),
             call('/fabric/ports/x9000c3r3j16p0'), call().json(),
             call('/fabric/ports/x9000c3r3j16p1'), call().json(),
             call('/fabric/ports/x9000c3r5j16p0'), call().json(),
             call('/fabric/ports/x9000c3r5j16p1'), call().json()]
        )

    def test_jack_not_in_port_list(self):
        """get_jack_port_data_list() with jack not in port list"""

        expected = []
        self.mock_get_ports.return_value = []
        result = self.pm.get_jack_port_data_list(['x9000c1r3j99'])
        self.assertEqual(result, expected)
        self.mock_cable_endpoints.load_cables_from_p2p_file.assert_called()
        self.mock_cable_endpoints.validate_jacks_using_p2p_file.assert_called()
        self.assertEqual(self.mock_cable_endpoints.get_cable.call_count, 1)
        self.assertEqual(self.mock_cable_endpoints.get_linked_jack_list.call_count, 1)
        self.mock_get_ports.assert_called()

    def tearDown(self):
        mock.patch.stopall()


class TestCreateOfflinePortPolicy(ExtendedTestCase):
    """Unit test for Switch create_offline_port_policy()."""

    def setUp(self):
        """Mock functions called."""

        self.mock_sat_session = mock.Mock()
        self.mock_fc_client_cls = mock.patch('sat.cli.swap.ports.SATSession').start()

        self.mock_fc_response = mock.Mock()
        self.mock_fc_response.json.return_value = {}
        self.mock_fc_client = mock.Mock()
        self.mock_fc_client.post.return_value = self.mock_fc_response
        self.mock_fc_client_cls = mock.patch('sat.cli.swap.ports.FabricControllerClient',
                                             return_value=self.mock_fc_client).start()

        self.mock_get_port_policies = mock.patch('sat.cli.swap.ports.PortManager.get_port_policies',
                                                 autospec=True).start()

        self.offline_edge_policy = os.path.join(os.path.dirname(EDGE_POLICY_LINK),
                                                f'sat-offline-{os.path.basename(EDGE_POLICY_LINK)}')
        self.mock_get_port_policies.return_value = [
            FABRIC_POLICY_LINK,
            EDGE_POLICY_LINK,
            self.offline_edge_policy
        ]

        self.mock_json_dumps = mock.patch('json.dumps', autospec=True).start()
        self.pm = PortManager()

    def tearDown(self):
        mock.patch.stopall()

    def test_basic(self):
        """Test create_offline_port_policy() that already exists"""
        with self.assertLogs(level=logging.INFO) as logs:
            self.pm.create_offline_port_policy(EDGE_POLICY_LINK, 'sat-offline-')
        self.assert_in_element(f'Using existing offline policy: {self.offline_edge_policy}',
                               logs.output)
        self.mock_get_port_policies.assert_called_once()
        self.mock_fc_client.post.assert_not_called()

    def test_new_policy(self):
        """Test create_offline_port_policy() that doesn't already exist"""
        with self.assertLogs(level=logging.DEBUG) as logs:
            self.pm.create_offline_port_policy(FABRIC_POLICY_LINK, 'sat-offline-')
        offline_fabric_policy = os.path.join(os.path.dirname(FABRIC_POLICY_LINK),
                                             f'sat-offline-{os.path.basename(FABRIC_POLICY_LINK)}')
        self.assert_in_element(f'Creating offline policy: {offline_fabric_policy}',
                               logs.output)
        self.mock_get_port_policies.assert_called_once()
        self.mock_fc_client.post.assert_called_once()


if __name__ == '__main__':
    unittest.main()
