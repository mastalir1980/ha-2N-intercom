"""Offline checks for the independent E2E SSDP description reader."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree

from _stubs import REPO_ROOT, load_module


class SsdpDescriptionClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests = types.ModuleType("requests")
        self.requests.get = Mock()
        auth = types.ModuleType("requests.auth")
        auth.HTTPBasicAuth = Mock()
        auth.HTTPDigestAuth = Mock()
        urllib3 = types.ModuleType("urllib3")
        urllib3.disable_warnings = Mock()
        urllib3.exceptions = types.SimpleNamespace(InsecureRequestWarning=Warning)
        with patch.dict(sys.modules, {
            "requests": self.requests,
            "requests.auth": auth,
            "urllib3": urllib3,
        }):
            module = load_module(
                "e2e_discovery_client_test",
                REPO_ROOT / "e2e" / "e2elib" / "twon.py",
            )
        self.client_type = module.TwoN
        self.client = self.client_type(
            "example.invalid", "test-user", "test-password", verify=True,
        )
        self.response = Mock(content=b"""\
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <manufacturer>2N, part of Axis group</manufacturer>
    <serialNumber>001122AABBCC</serialNumber>
    <UDN>uuid:device-001122AABBCC</UDN>
  </device>
</root>""")
        self.requests.get.return_value = self.response

    def test_reads_namespaced_description_without_auth(self) -> None:
        self.assertEqual(self.client.ssdp_description(), {
            "manufacturer": "2N, part of Axis group",
            "serialNumber": "001122AABBCC",
            "UDN": "uuid:device-001122AABBCC",
        })
        self.requests.get.assert_called_once_with(
            "https://example.invalid/ssdp_server/description.xml",
            verify=True,
            timeout=10,
        )
        self.response.raise_for_status.assert_called_once_with()

    def test_uses_client_protocol_and_verify_settings(self) -> None:
        client = self.client_type(
            "example.invalid", "test-user", "test-password",
            protocol="http", verify=False,
        )
        client.ssdp_description()
        self.requests.get.assert_called_once_with(
            "http://example.invalid/ssdp_server/description.xml",
            verify=False,
            timeout=10,
        )

    def test_http_failure_is_propagated_before_parsing(self) -> None:
        self.response.raise_for_status.side_effect = RuntimeError("HTTP 404")
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            self.client.ssdp_description()

    def test_invalid_xml_is_not_treated_as_empty_description(self) -> None:
        self.response.content = b"<root"
        with self.assertRaises(ElementTree.ParseError):
            self.client.ssdp_description()

    def test_missing_fields_fail_without_echoing_identifiers(self) -> None:
        self.response.content = b"""\
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device><manufacturer>2N, part of Axis group</manufacturer></device>
</root>"""
        with self.assertRaisesRegex(ValueError, "^SSDP description is missing serialNumber$"):
            self.client.ssdp_description()
