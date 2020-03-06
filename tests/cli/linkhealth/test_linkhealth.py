"""
Unit tests for the sat.sat.cli.linkhealth.main functions.

Copyright 2019-2020 Cray Inc. All Rights Reserved.
"""


import json
import os
import unittest
from unittest import mock
from argparse import Namespace
from sat.apiclient import APIError
from sat.xname import XName

import sat.cli.linkhealth.main


def set_options(namespace):
    """Set default options for Namespace."""
    namespace.xnames = []
    namespace.xname_file = ""
    namespace.redfish_username = "yogibear"
    namespace.no_borders = True
    namespace.no_headings = False
    namespace.format = 'pretty'
    namespace.reverse = object()
    namespace.sort_by = object()
    namespace.filter_strs = object()


class FakeReport:
    """Used for mocking the return from get_report."""
    def get_yaml(self):
        return '---'


class FakeRequest:
    """Used for mocking the return from HSMClient.get, which is a Request.
    """

    def json(self):
        endpoints = [
            {'ID': 'x1000c1'},
            {'ID': 'x2000c2'},
            {'ID': 'x3000c3'},
            {'ID': 'x4000c4'},
        ]
        return {'RedfishEndpoints': endpoints}


class TestLinkhealthGetRouterXnames(unittest.TestCase):
    """Unit test for linkhealth get_router_xnames().

    These tests have more to do with outlining the expected elements
    returned by the functions that get_router_xnames relies on.
    """

    @mock.patch('sat.cli.linkhealth.main.HSMClient.get', return_value=FakeRequest())
    def test_get_xnames_router_bmc(self, get_mocker):
        """It should filter its results using a RouterBMC filter.

        A sat.apiclient.HSMClient instance is responsible for this - and this
        test cements the arguments provided to that call.
        """
        xnames = sat.cli.linkhealth.main.get_router_xnames()
        get_mocker.assert_called_once_with('Inventory', 'RedfishEndpoints', params={'type': 'RouterBMC'})

    @mock.patch('sat.cli.linkhealth.main.HSMClient.get', return_value=FakeRequest())
    @mock.patch(__name__ + '.FakeRequest.json', return_value={'RedfishEndpoints': [{'Not ID': None}]})
    def test_get_xnames_no_ids(self, get_mocker, json_mocker):
        """It should not return RedfishEndpoints that don't have an ID key.
        """
        xnames = sat.cli.linkhealth.main.get_router_xnames()
        get_mocker.assert_called_once()
        json_mocker.assert_called_once()

        self.assertEqual(0, len(xnames))

    @mock.patch('sat.cli.linkhealth.main.HSMClient.get', side_effect=sat.apiclient.APIError)
    def test_api_error(self, get_mocker):
        """It should raise an APIError if the client's get raises an APIError.
        """
        with self.assertRaises(sat.apiclient.APIError):
            xnames = sat.cli.linkhealth.main.get_router_xnames()
        get_mocker.assert_called_once()

    @mock.patch('sat.cli.linkhealth.main.HSMClient.get', return_value=FakeRequest())
    @mock.patch(__name__ + '.FakeRequest.json', return_value={'Not RedfishEndpoints': None})
    def test_incorrect_result(self, get_mocker, json_mocker):
        """It should raise a KeyError if the JSON contains unexpected entries.

        More specifically, the JSON needs to be a dictionary whose top level
        contains entries under a key called 'RedfishEndpoints'.
        """
        with self.assertRaises(KeyError):
            xnames = sat.cli.linkhealth.main.get_router_xnames()

        get_mocker.assert_called_once()
        json_mocker.assert_called_once()

    @mock.patch('sat.cli.linkhealth.main.HSMClient.get', return_value=FakeRequest())
    @mock.patch(__name__ + '.FakeRequest.json', side_effect=ValueError)
    def test_invalid_json(self, get_mocker, json_mocker):
        """It should raise a ValueError if the result is not valid JSON.

        The client.get(...).json() will raise a ValueError if its payload
        was invalid json. In this case, the get_router_xnames should just
        bucket brigade with a custom message.
        """
        with self.assertRaises(ValueError):
            xnames = sat.cli.linkhealth.main.get_router_xnames()
        get_mocker.assert_called_once()
        json_mocker.assert_called_once()


class TestLinkhealthGetMatches(unittest.TestCase):

    def test_get_matches_chassis(self):
        """Test Linkhealth: get_matches() with chassis filter."""
        filters = [XName('x1000c1'), XName('x2000c2')]
        elems = [XName('x1000c1r1b1'), XName('x1000c2r2b2')]
        used, unused, matches, no_matches = sat.cli.linkhealth.main.get_matches(filters, elems)
        self.assertEqual({XName('x1000c1')}, used)
        self.assertEqual({XName('x2000c2')}, unused)
        self.assertEqual({XName('x1000c1r1b1')}, matches)
        self.assertEqual({XName('x1000c2r2b2')}, no_matches)

    def test_get_matches_bmc(self):
        """Test Linkhealth: get_matches() with BMC filter."""
        filters = [XName('x1000c1r1b1'), XName('x2000c2r2b2')]
        elems = [XName('x1000c1r1b1'), XName('x1000c2r2b2')]
        used, unused, matches, no_matches = sat.cli.linkhealth.main.get_matches(filters, elems)
        self.assertEqual({XName('x1000c1r1b1')}, used)
        self.assertEqual({XName('x2000c2r2b2')}, unused)
        self.assertEqual({XName('x1000c1r1b1')}, matches)
        self.assertEqual({XName('x1000c2r2b2')}, no_matches)

    def test_get_matches_empty_filters(self):
        """Test Linkhealth: get_matches() with empty filter."""
        filters = []
        elems = [XName('x1000c1r1b1'), XName('x1000c2r2b2')]
        used, unused, matches, no_matches = sat.cli.linkhealth.main.get_matches(filters, elems)
        self.assertEqual(set(), used)
        self.assertEqual(set(), unused)
        self.assertEqual(set(), matches)
        self.assertEqual(set(elems), no_matches)

    def test_get_matches_no_elems(self):
        """Test Linkhealth: get_matches() with no elements."""
        filters = [XName('x1000c1r1b1'), XName('x2000c2r2b2')]
        elems = []
        used, unused, matches, no_matches = sat.cli.linkhealth.main.get_matches(filters, elems)
        self.assertEqual(set(), used)
        self.assertEqual(set(filters), unused)
        self.assertEqual(set(), matches)
        self.assertEqual(set(), no_matches)


class TestDoLinkhealth(unittest.TestCase):
    """Unit test for linkhealth do_linkhealth()."""

    def setUp(self):
        """Mock things outside of do_linkhealth."""

        self.mock_log_debug = mock.patch('sat.logging.LOGGER.debug',
                                         autospec=True).start()
        self.mock_log_error = mock.patch('sat.logging.LOGGER.error',
                                         autospec=True).start()

        self.mock_bmc_xnames = [XName('x1000c0r0b0'), XName('x1000c12r13b14'), XName('x3000c0r0b0')]
        self.mock_get_router_xnames = mock.patch(
            'sat.cli.linkhealth.main.get_router_xnames',
            autospec=True).start()
        self.mock_get_router_xnames.return_value = self.mock_bmc_xnames

        self.mock_port_mappings = {'x1000c0r0b0j0p0': ['addr-stuff']}
        self.mock_get_jack_port_ids = mock.patch(
            'sat.cli.linkhealth.main.get_jack_port_ids',
            autospec=True).start()
        self.mock_get_jack_port_ids.return_value = self.mock_port_mappings

        self.mock_get_username_and_pass = mock.patch(
            'sat.redfish.get_username_and_pass',
            autospec=True).start()
        self.mock_get_username_and_pass.return_value = ('ginger', 'Spice32')

        self.mock_query = mock.patch(
            'sat.redfish.query',
            autospec=True).start()
        self.mock_query.return_value = ('url', {'Members': []})

        self.mock_disable_warnings = mock.patch(
            'urllib3.disable_warnings',
            autospec=True).start()

        self.mock_report_cls = mock.patch('sat.cli.linkhealth.main.Report',
                                          autospec=True).start()
        self.mock_report_obj = self.mock_report_cls.return_value

        self.mock_get_report = mock.patch('sat.cli.linkhealth.main.get_report',
                                          autospec=True).start()
        self.mock_get_report.return_value = FakeReport()

        self.mock_print = mock.patch('builtins.print', autospec=True).start()

        self.parsed = Namespace()
        set_options(self.parsed)

    def tearDown(self):
        mock.patch.stopall()

    def test_no_xname_option(self):
        """Test Linkhealth: do_linkhealth() no xname option"""
        sat.cli.linkhealth.main.do_linkhealth(self.parsed)
        self.mock_get_router_xnames.assert_called_once()
        # List returned by get_router_xnames becomes argument:
        self.mock_get_jack_port_ids.assert_called_once_with(self.mock_bmc_xnames,
            'ginger', 'Spice32')
        self.mock_get_report.assert_called_once()
        self.mock_print.assert_called_once()

    def test_no_xname_option_yaml(self):
        """Test Linkhealth: do_linkhealth() no xname option, yaml output"""
        self.parsed.format = 'yaml'
        sat.cli.linkhealth.main.do_linkhealth(self.parsed)
        self.mock_get_router_xnames.assert_called_once()
        self.mock_get_jack_port_ids.assert_called_once_with(
            self.mock_bmc_xnames, 'ginger', 'Spice32')
        self.mock_get_report.assert_called_once()
        self.mock_print.assert_called_once()

    def test_with_one_xname(self):
        """Test Linkhealth: do_linkhealth() with one xname"""
        self.parsed.xnames = ['x1000c12r13b14']
        sat.cli.linkhealth.main.do_linkhealth(self.parsed)
        self.mock_get_router_xnames.assert_called_once()
        # Set returned by get_matches becomes argument.
        self.mock_get_jack_port_ids.assert_called_once_with(
            {XName('x1000c12r13b14')}, 'ginger', 'Spice32')
        self.mock_get_report.assert_called_once()
        self.mock_print.assert_called_once()

    def test_with_two_xnames(self):
        """Test Linkhealth: do_linkhealth() with two xnames"""
        self.parsed.xnames = ['x1000c12r13b14', 'x3000c0r0b0']
        sat.cli.linkhealth.main.do_linkhealth(self.parsed)
        # Set returned by get_matches becomes argument.
        self.mock_get_router_xnames.assert_called_once()
        self.mock_get_jack_port_ids.assert_called_once_with(
            {XName('x1000c12r13b14'), XName('x3000c0r0b0')}, 'ginger', 'Spice32')
        self.mock_get_report.assert_called_once()
        self.mock_print.assert_called_once()

    def test_with_xname_option_yaml(self):
        """Test Linkhealth: do_linkhealth() with xname option, yaml output"""
        self.parsed.xnames = ['x1000c12r13b14']
        self.parsed.format = 'yaml'
        sat.cli.linkhealth.main.do_linkhealth(self.parsed)
        self.mock_get_router_xnames.assert_called_once()
        # Set returned by get_matches becomes argument.
        self.mock_get_jack_port_ids.assert_called_once_with(
            {XName('x1000c12r13b14')}, 'ginger', 'Spice32')
        self.mock_get_report.assert_called_once()
        self.mock_print.assert_called_once()

    def test_get_router_xnames_exception(self):
        """Test Linkhealth: do_linkhealth() get_router_names exception"""
        self.mock_get_router_xnames.side_effect = APIError
        with self.assertRaises(SystemExit):
            sat.cli.linkhealth.main.do_linkhealth(self.parsed)

    def test_no_jack_port_ids(self):
        """Test Linkhealth: do_linkhealth() no jack port IDs"""
        self.mock_get_jack_port_ids.return_value = []
        with self.assertRaises(SystemExit):
            sat.cli.linkhealth.main.do_linkhealth(self.parsed)


if __name__ == '__main__':
    unittest.main()
