"""Unit tests for camera transport helpers in api.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from itertools import product
import json
import logging
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from _stubs import (
    API_PATH,
    CONST_PATH,
    ensure_package,
    install_api_stubs,
    load_module,
)


def load_api_module():
    install_api_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    return load_module("custom_components.2n_intercom.api", API_PATH)


class DeviceErrorParserTests(unittest.TestCase):
    """Unit tests for the centralized 2N error-payload parser.

    These guard the only place in the integration that decides whether
    a non-success response is "fine, ignore it" or "warning, action
    failed". The 2N firmware overloads ``code 14`` for at least two
    distinct conditions, so the parser MUST disambiguate by description
    string and not by code alone.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def test_parse_returns_none_for_success_payload(self) -> None:
        self.assertIsNone(
            self.api_module.parse_device_error({"success": True, "result": {}})
        )

    def test_parse_returns_none_for_non_dict_payload(self) -> None:
        self.assertIsNone(self.api_module.parse_device_error(None))
        self.assertIsNone(self.api_module.parse_device_error("oops"))

    def test_parse_extracts_code_description_and_param(self) -> None:
        error = self.api_module.parse_device_error(
            {
                "success": False,
                "error": {
                    "code": 11,
                    "description": "missing mandatory parameter",
                    "param": "session",
                },
            }
        )
        assert error is not None
        self.assertEqual(error.code, 11)
        self.assertEqual(error.description, "missing mandatory parameter")
        self.assertEqual(error.param, "session")

    def test_parse_handles_success_false_without_error_block(self) -> None:
        error = self.api_module.parse_device_error({"success": False})
        assert error is not None
        self.assertIsNone(error.code)
        self.assertEqual(error.description, "")
        self.assertIsNone(error.param)

    def test_session_not_found_is_recognised_as_idempotent(self) -> None:
        error = self.api_module.parse_device_error(
            {
                "success": False,
                "error": {"code": 14, "description": "session not found"},
            }
        )
        assert error is not None
        self.assertTrue(error.is_unspecified_session_not_found())

    def test_unsupported_content_type_is_NOT_idempotent(self) -> None:
        """Code 14 is overloaded; ``Unsupported Content-Type`` means the
        request was REJECTED, not that the post-condition was met. The
        previous blanket ``if code == 14: return True`` shortcut masked
        this for months — see commit a5fe738."""
        error = self.api_module.parse_device_error(
            {
                "success": False,
                "error": {
                    "code": 14,
                    "description": "Unsupported Content-Type",
                },
            }
        )
        assert error is not None
        self.assertFalse(error.is_unspecified_session_not_found())

    def test_other_codes_never_treated_as_idempotent_session_not_found(self) -> None:
        for code, desc in (
            (8, "invalid authentication method"),
            (11, "missing mandatory parameter"),
            (12, "invalid parameter value"),
            (None, ""),
        ):
            with self.subTest(code=code):
                error = self.api_module.parse_device_error(
                    {
                        "success": False,
                        "error": {"code": code, "description": desc},
                    }
                )
                assert error is not None
                self.assertFalse(error.is_unspecified_session_not_found())

    def test_format_renders_present_fields_only(self) -> None:
        cls = self.api_module.TwoNDeviceError
        self.assertEqual(cls(code=14, description="", param=None).format(), "code=14")
        self.assertEqual(
            cls(code=11, description="missing mandatory parameter", param="session").format(),
            "code=11 description='missing mandatory parameter' param='session'",
        )


class CameraTransportApiTests(unittest.TestCase):
    """Tests for pure camera transport helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def test_parse_camera_caps_extracts_resolutions_and_sources(self) -> None:
        payload = {
            "success": True,
            "result": {
                "jpeg": {
                    "resolutions": [
                        "176x144",
                        {"width": 1280, "height": 960},
                        {"width": "640", "height": "480"},
                    ]
                },
                "sources": {
                    "available": ["internal", "external"],
                },
            },
        }

        caps = self.api_module.parse_camera_caps(payload)

        self.assertEqual(
            [resolution.as_tuple() for resolution in caps.jpeg_resolutions],
            [(176, 144), (1280, 960), (640, 480)],
        )
        self.assertEqual(caps.sources, ("internal", "external"))

    def test_invalid_fps_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.api_module.validate_mjpeg_fps(0)

        with self.assertRaises(ValueError):
            self.api_module.validate_mjpeg_fps(16)

    def test_build_mjpeg_url_includes_expected_query(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user@example.com",
            password="p@ss word",
            port=8443,
            protocol="https",
        )

        # Default must NOT embed credentials. The camera entity passes
        # username/password to MjpegCamera separately so logs and HA
        # diagnostics never see them in the URL.
        url = api.build_mjpeg_url(width=640, height=480, fps=7, source="internal")

        self.assertEqual(
            url,
            "https://intercom.local:8443"
            "/api/camera/snapshot?source=internal&width=640&height=480&fps=7",
        )
        self.assertNotIn("user", url)
        self.assertNotIn("p%40ss", url)

    def test_build_mjpeg_url_can_omit_credentials(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user@example.com",
            password="p@ss word",
            port=8443,
            protocol="https",
        )

        url = api.build_mjpeg_url(
            width=640,
            height=480,
            fps=7,
            source="internal",
            include_auth=False,
        )

        self.assertEqual(
            url,
            "https://intercom.local:8443"
            "/api/camera/snapshot?source=internal&width=640&height=480&fps=7",
        )

    def test_transport_selection_prefers_rtsp_then_mjpeg_then_jpeg_only(self) -> None:
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=True,
                mjpeg_available=True,
            ),
            self.api_module.LIVE_VIEW_MODE_RTSP,
        )
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=False,
                mjpeg_available=True,
            ),
            self.api_module.LIVE_VIEW_MODE_MJPEG,
        )
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=False,
                mjpeg_available=False,
            ),
            self.api_module.LIVE_VIEW_MODE_JPEG_ONLY,
        )


class CameraTransportProbeRetryTests(unittest.IsolatedAsyncioTestCase):
    """Tests for transport detection behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    async def test_resolved_jpeg_only_result_is_cached(self) -> None:
        api_module = self.api_module

        class ProbeApi(api_module.TwoNIntercomAPI):
            def __init__(self) -> None:
                super().__init__(
                    host="intercom.local",
                    username="user",
                    password="secret",
                )
                self._rtsp_results = [False]
                self._mjpeg_results = [False]
                self._public_results = [False]

            async def async_get_camera_caps(self, *, force_refresh: bool = False):
                return api_module.CameraCapabilities()

            async def async_probe_rtsp(self) -> bool:
                return self._rtsp_results.pop(0)

            async def async_probe_mjpeg(self, **kwargs) -> bool:
                return self._mjpeg_results.pop(0)

            async def async_probe_mjpeg_public(self, **kwargs) -> bool:
                return self._public_results.pop(0)

        api = ProbeApi()

        first = await api.async_get_camera_transport_info()
        self.assertTrue(first.resolved)
        self.assertEqual(first.selected_mode, api_module.LIVE_VIEW_MODE_JPEG_ONLY)

        second = await api.async_get_camera_transport_info()
        self.assertTrue(second.resolved)
        self.assertEqual(second.selected_mode, api_module.LIVE_VIEW_MODE_JPEG_ONLY)

    async def test_async_probe_rtsp_treats_403_forbidden_as_unavailable(self) -> None:
        api_module = self.api_module

        class FakeReader:
            def __init__(self, response: bytes) -> None:
                self.response = response

            async def read(self, size: int) -> bytes:
                return self.response

        class FakeWriter:
            def __init__(self) -> None:
                self.buffer = bytearray()
                self.closed = False
                self.wait_closed_called = False

            def write(self, data: bytes) -> None:
                self.buffer.extend(data)

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                self.closed = True

            async def wait_closed(self) -> None:
                self.wait_closed_called = True

        api = api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
        )
        response = (
            b"RTSP/1.0 403 Forbidden\r\n"
            b"Server: HIP 2.50.0.76.2\r\n"
            b"Content-Length: 0\r\n\r\n"
        )

        async def fake_open_connection(host: str, port: int):
            return FakeReader(response), FakeWriter()

        async def fake_wait_for(awaitable, timeout):
            return await awaitable

        with patch.object(api_module.asyncio, "open_connection", fake_open_connection), patch.object(
            api_module.asyncio, "wait_for", fake_wait_for
        ):
            result = await api.async_probe_rtsp()

        self.assertFalse(result)

    async def test_async_probe_rtsp_accepts_200_ok_as_available(self) -> None:
        api_module = self.api_module

        class FakeReader:
            def __init__(self, response: bytes) -> None:
                self.response = response

            async def read(self, size: int) -> bytes:
                return self.response

        class FakeWriter:
            def __init__(self) -> None:
                self.buffer = bytearray()
                self.closed = False
                self.wait_closed_called = False

            def write(self, data: bytes) -> None:
                self.buffer.extend(data)

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                self.closed = True

            async def wait_closed(self) -> None:
                self.wait_closed_called = True

        api = api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
            rtsp_username="rtspuser",
            rtsp_password="rtspsecret",
        )
        response = (
            b"RTSP/1.0 200 OK\r\n"
            b"Server: HIP 2.50.0.76.2\r\n"
            b"Content-Length: 0\r\n\r\n"
        )

        async def fake_open_connection(host: str, port: int):
            return FakeReader(response), FakeWriter()

        async def fake_wait_for(awaitable, timeout):
            return await awaitable

        with patch.object(api_module.asyncio, "open_connection", fake_open_connection), patch.object(
            api_module.asyncio, "wait_for", fake_wait_for
        ):
            result = await api.async_probe_rtsp()

        self.assertTrue(result)

    async def test_async_probe_rtsp_returns_false_without_rtsp_credentials(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
        )
        result = await api.async_probe_rtsp()
        self.assertFalse(result)


class CallControlApiTests(unittest.IsolatedAsyncioTestCase):
    """Tests for call-control helpers in api.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def _make_api(self, response_payload: dict[str, object] | None = None):
        api_module = self.api_module

        class FakeResponse:
            status = 200
            headers: dict[str, str] = {}

            def __init__(self, payload: dict[str, object] | None) -> None:
                self._payload = payload or {"success": True}

            async def json(self) -> dict[str, object]:
                return self._payload

            def raise_for_status(self) -> None:
                return None

        class CallApi(api_module.TwoNIntercomAPI):
            def __init__(self) -> None:
                super().__init__(
                    host="intercom.local",
                    username="user",
                    password="secret",
                    port=443,
                    protocol="https",
                )
                self.requests: list[dict[str, object]] = []
                self.response = FakeResponse(response_payload)

            @asynccontextmanager
            async def _async_request(
                self,
                method: str,
                path: str,
                *,
                params=None,
                json_data=None,
                headers=None,
            ):
                self.requests.append(
                    {
                        "method": method,
                        "path": path,
                        "params": params,
                        "json_data": json_data,
                        "headers": headers,
                    }
                )
                yield self.response

        return CallApi()

    async def test_answer_call_sends_session_id(self) -> None:
        api = self._make_api()

        result = await api.async_answer_call("session-123")

        self.assertTrue(result)
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/call/answer",
                    "params": {"session": "session-123"},
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_answer_call_returns_false_when_device_reports_failure(self) -> None:
        api = self._make_api({"success": False})

        result = await api.async_answer_call("session-123")

        self.assertFalse(result)

    async def test_hangup_call_sends_only_session_id_by_default(self) -> None:
        """The default hangup must be a GET with only ``session=`` because
        firmware 2.50.0.76.2 silently no-ops POSTs and ignores the ``reason``
        param for outgoing-ringing sessions while still answering ``success``.
        """
        api = self._make_api()

        result = await api.async_hangup_call("session-456")

        self.assertTrue(result)
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/call/hangup",
                    "params": {"session": "session-456"},
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_hangup_call_forwards_explicit_reason_when_provided(self) -> None:
        api = self._make_api()

        result = await api.async_hangup_call("session-456", reason="busy")

        self.assertTrue(result)
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/call/hangup",
                    "params": {"session": "session-456", "reason": "busy"},
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_hangup_call_returns_false_when_device_reports_failure(self) -> None:
        api = self._make_api({"success": False})

        result = await api.async_hangup_call("session-456", reason="busy")

        self.assertFalse(result)

    async def test_hangup_call_treats_session_not_found_as_success(self) -> None:
        """Code 14 + ``session not found`` is the firmware's way of saying
        the desired post-condition (no such call) is already true. We treat
        that as success so the integration is idempotent across races
        between push (log subscription) and pull (status polling)."""
        api = self._make_api(
            {
                "success": False,
                "error": {"code": 14, "description": "session not found"},
            }
        )

        result = await api.async_hangup_call("session-stale")

        self.assertTrue(result)

    async def test_hangup_call_treats_unsupported_content_type_as_failure(self) -> None:
        """Code 14 is **overloaded** by the 2N firmware. The variant we
        must NEVER treat as success is ``"Unsupported Content-Type"`` —
        that means the request was rejected outright and the call is still
        ringing. A previous version of this code returned True for *any*
        code-14 response, which silently masked the aiohttp default-POST
        bug for months."""
        api = self._make_api(
            {
                "success": False,
                "error": {"code": 14, "description": "Unsupported Content-Type"},
            }
        )

        result = await api.async_hangup_call("session-live")

        self.assertFalse(result)

    async def test_hangup_call_logs_warning_with_full_device_error(self) -> None:
        """Genuine action failures must surface as WARNING in the log,
        carrying the full ``code/description/param`` payload so the user
        can grep ``ha:2n_intercom`` and immediately see what the device
        rejected. Idempotent ``session not found`` is the only flavour
        that may stay at DEBUG."""
        api = self._make_api(
            {
                "success": False,
                "error": {
                    "code": 14,
                    "description": "Unsupported Content-Type",
                },
            }
        )

        with self.assertLogs(
            "custom_components.2n_intercom.api", level="WARNING"
        ) as captured:
            result = await api.async_hangup_call("session-live")

        self.assertFalse(result)
        joined = "\n".join(captured.output)
        self.assertIn("rejected by device", joined)
        self.assertIn("code=14", joined)
        self.assertIn("Unsupported Content-Type", joined)

    async def test_hangup_call_session_not_found_does_NOT_warn(self) -> None:
        api = self._make_api(
            {
                "success": False,
                "error": {"code": 14, "description": "session not found"},
            }
        )

        with self.assertNoLogs(
            "custom_components.2n_intercom.api", level="WARNING"
        ):
            result = await api.async_hangup_call("session-stale")

        self.assertTrue(result)

    async def test_get_phone_status_logs_warning_on_device_failure(self) -> None:
        """Read endpoints used to swallow ``success: false`` and return
        ``{}``, which made an unauthenticated/unauthorised firmware look
        identical to "device has no SIP accounts". The remediation routes
        every rejection through the same parser as the action endpoints
        and emits a WARNING with the full code/description so users can
        grep ``ha:2n_intercom`` and immediately see what was rejected."""
        api = self._make_api(
            {
                "success": False,
                "error": {
                    "code": 8,
                    "description": "invalid authentication method",
                },
            }
        )

        with self.assertLogs(
            "custom_components.2n_intercom.api", level="WARNING"
        ) as captured:
            result = await api.async_get_phone_status()

        self.assertEqual(result, {})
        joined = "\n".join(captured.output)
        self.assertIn("phone status", joined)
        self.assertIn("rejected by device", joined)
        self.assertIn("code=8", joined)
        self.assertIn("invalid authentication method", joined)

    async def test_switch_control_logs_warning_with_param_on_device_failure(self) -> None:
        """The user-facing door-opener path: a button press that the
        firmware refuses MUST surface as a WARNING containing the
        relay/action and the parsed code/description/param payload —
        this is the most user-visible failure mode and used to be
        completely silent."""
        api = self._make_api(
            {
                "success": False,
                "error": {
                    "code": 11,
                    "param": "switch",
                    "description": "missing mandatory parameter",
                },
            }
        )

        with self.assertLogs(
            "custom_components.2n_intercom.api", level="WARNING"
        ) as captured:
            result = await api.async_switch_control(relay=1, action="on")

        self.assertFalse(result)
        joined = "\n".join(captured.output)
        self.assertIn("switch control relay=1 action=on", joined)
        self.assertIn("rejected by device", joined)
        self.assertIn("code=11", joined)
        self.assertIn("param='switch'", joined)
        self.assertIn("missing mandatory parameter", joined)

    async def test_io_control_sends_on_and_off_query_params(self) -> None:
        for on, action in ((True, "on"), (False, "off")):
            with self.subTest(on=on):
                api = self._make_api()
                self.assertTrue(await api.async_io_control("modul1.relay1", on))
                self.assertEqual(
                    api.requests,
                    [{
                        "method": "GET",
                        "path": "/api/io/ctrl",
                        "params": {"port": "modul1.relay1", "action": action},
                        "json_data": None,
                        "headers": None,
                    }],
                )

    async def test_io_control_logs_device_error_at_warning(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {
                "code": 11,
                "description": "missing mandatory parameter",
                "param": "port",
            },
        })
        with self.assertLogs(
            "custom_components.2n_intercom.api", level="WARNING"
        ) as captured:
            self.assertFalse(await api.async_io_control("output1", True))
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.WARNING)
        message = captured.output[0]
        for expected in (
            "/api/io/ctrl", "port=output1", "action=on", "code=11",
            "missing mandatory parameter", "param='port'",
        ):
            self.assertIn(expected, message)

    async def test_io_control_timeout_and_transport_errors(self) -> None:
        errors = (
            (TimeoutError("timed out"), "timed out"),
            (self.api_module.aiohttp.ClientError("HTTP 401"), "transport error"),
        )
        for error, expected in errors:
            with self.subTest(error=error):
                api = self._make_api()
                api.response.raise_for_status = Mock(side_effect=error)
                with self.assertLogs(
                    "custom_components.2n_intercom.api", level="WARNING"
                ) as captured:
                    self.assertFalse(await api.async_io_control("output1", False))
                self.assertIn(expected, captured.output[0])
                self.assertEqual(captured.records[0].levelno, logging.WARNING)
                api.response.raise_for_status.assert_called_once_with()

    async def test_io_control_unexpected_error_is_logged(self) -> None:
        api = self._make_api()
        api.response.raise_for_status = Mock(side_effect=ValueError("bad response"))
        with self.assertLogs(
            "custom_components.2n_intercom.api", level="ERROR"
        ) as captured:
            self.assertFalse(await api.async_io_control("output1", True))
        self.assertIn("unexpected error", captured.output[0])

    async def test_get_phone_status_returns_result_payload(self) -> None:
        api = self._make_api(
            {
                "success": True,
                "result": {
                    "accounts": [
                        {"account": 1, "enabled": True, "registered": True}
                    ]
                },
            }
        )

        result = await api.async_get_phone_status()

        self.assertEqual(result, {"accounts": [{"account": 1, "enabled": True, "registered": True}]})
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/phone/status",
                    "params": None,
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_get_switch_caps_returns_result_payload(self) -> None:
        api = self._make_api(
            {
                "success": True,
                "result": {
                    "switches": [
                        {"switch": 1, "enabled": True, "mode": "monostable"}
                    ]
                },
            }
        )

        result = await api.async_get_switch_caps()

        self.assertEqual(
            result,
            {"switches": [{"switch": 1, "enabled": True, "mode": "monostable"}]},
        )
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/switch/caps",
                    "params": None,
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_get_switch_status_returns_result_payload(self) -> None:
        api = self._make_api(
            {
                "success": True,
                "result": {
                    "switches": [
                        {"switch": 1, "active": False, "locked": False, "held": False}
                    ]
                },
            }
        )

        result = await api.async_get_switch_status()

        self.assertEqual(
            result,
            {"switches": [{"switch": 1, "active": False, "locked": False, "held": False}]},
        )
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/switch/status",
                    "params": None,
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_get_io_caps_returns_result_payload(self) -> None:
        api = self._make_api(
            {
                "success": True,
                "result": {
                    "ports": [{"port": "relay1", "type": "output"}]
                },
            }
        )

        result = await api.async_get_io_caps()

        self.assertEqual(result, {"ports": [{"port": "relay1", "type": "output"}]})
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/io/caps",
                    "params": None,
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_get_io_status_returns_result_payload(self) -> None:
        api = self._make_api(
            {
                "success": True,
                "result": {
                    "ports": [{"port": "relay1", "state": 0}]
                },
            }
        )

        result = await api.async_get_io_status()

        self.assertEqual(result, {"ports": [{"port": "relay1", "state": 0}]})
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/io/status",
                    "params": None,
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_subscribe_log_sends_filter_and_returns_subscription_id(self) -> None:
        api = self._make_api({"success": True, "result": {"id": 287363148}})

        result = await api.async_subscribe_log(
            ["CallStateChanged", "CallSessionStateChanged"]
        )

        self.assertEqual(result, 287363148)
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/log/subscribe",
                    "params": {
                        "filter": "CallStateChanged,CallSessionStateChanged",
                    },
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_pull_log_sends_id_and_timeout_and_returns_events(self) -> None:
        api = self._make_api(
            {
                "success": True,
                "result": {
                    "events": [{"event": "CallStateChanged", "params": {"state": "ringing"}}]
                },
            }
        )

        result = await api.async_pull_log(287363148, timeout=5)

        self.assertEqual(
            result,
            [{"event": "CallStateChanged", "params": {"state": "ringing"}}],
        )
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/log/pull",
                    "params": {"id": 287363148, "timeout": 5},
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_unsubscribe_log_sends_id_and_returns_success(self) -> None:
        api = self._make_api({"success": True})

        result = await api.async_unsubscribe_log(287363148)

        self.assertTrue(result)
        self.assertEqual(
            api.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/log/unsubscribe",
                    "params": {"id": 287363148},
                    "json_data": None,
                    "headers": None,
                }
            ],
        )

    async def test_probe_mjpeg_uses_authenticated_request_flow(self) -> None:
        api_module = self.api_module

        class FakeResponse:
            status = 200
            headers = {
                "Content-Type": "multipart/x-mixed-replace; boundary=jpeg-video-boundary"
            }

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def raise_for_status(self) -> None:
                return None

        api = api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user@example.com",
            password="secret word",
            port=8443,
            protocol="https",
        )

        calls: list[tuple[str, str, dict[str, object] | None, dict[str, str] | None]] = []

        def fake_async_request(method, path, *, params=None, json_data=None, headers=None):
            calls.append((method, path, params, headers))

            class _ContextManager:
                async def __aenter__(self_inner):
                    return FakeResponse()

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

            return _ContextManager()

        api._async_request = fake_async_request  # type: ignore[method-assign]

        result = await api.async_probe_mjpeg(
            capabilities=api_module.CameraCapabilities(),
            width=640,
            height=480,
            fps=10,
            source="internal",
        )

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [
                (
                    "GET",
                    "/api/camera/snapshot",
                    {
                        "source": "internal",
                        "width": 640,
                        "height": 480,
                        "fps": 10,
                    },
                    {"Accept": "multipart/x-mixed-replace,image/jpeg"},
                )
            ],
        )

    async def test_probe_mjpeg_public_uses_unauthenticated_request_flow(self) -> None:
        api_module = self.api_module

        class FakeResponse:
            status = 200
            headers = {
                "Content-Type": "multipart/x-mixed-replace; boundary=jpeg-video-boundary"
            }

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def raise_for_status(self) -> None:
                return None

        api = api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user@example.com",
            password="secret word",
            port=8443,
            protocol="https",
        )

        calls: list[tuple[str, str, dict[str, object] | None, dict[str, str] | None]] = []

        def fake_async_request_without_auth(
            method,
            path,
            *,
            params=None,
            json_data=None,
            headers=None,
        ):
            del json_data
            calls.append((method, path, params, headers))

            class _ContextManager:
                async def __aenter__(self_inner):
                    return FakeResponse()

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

            return _ContextManager()

        api._async_request_without_auth = fake_async_request_without_auth  # type: ignore[method-assign]

        result = await api.async_probe_mjpeg_public(
            capabilities=api_module.CameraCapabilities(),
            width=640,
            height=480,
            fps=10,
            source="internal",
        )

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [
                (
                    "GET",
                    "/api/camera/snapshot",
                    {
                        "source": "internal",
                        "width": 640,
                        "height": 480,
                        "fps": 10,
                    },
                    {"Accept": "multipart/x-mixed-replace,image/jpeg"},
                )
            ],
        )

    async def test_public_mjpeg_only_still_selects_mjpeg_transport(self) -> None:
        api_module = self.api_module

        class ProbeApi(api_module.TwoNIntercomAPI):
            async def async_get_camera_caps(self, *, force_refresh: bool = False):
                return api_module.CameraCapabilities()

            async def async_probe_rtsp(self) -> bool:
                return False

            async def async_probe_mjpeg(self, **kwargs) -> bool:
                return False

            async def async_probe_mjpeg_public(self, **kwargs) -> bool:
                return True

        api = ProbeApi(
            host="intercom.local",
            username="user",
            password="secret",
        )

        transport_info = await api.async_get_camera_transport_info()

        self.assertTrue(transport_info.resolved)
        self.assertTrue(transport_info.live_view_available)
        self.assertTrue(transport_info.mjpeg_available)
        self.assertTrue(transport_info.mjpeg_public_url_available)
        self.assertEqual(transport_info.selected_mode, api_module.LIVE_VIEW_MODE_MJPEG)


class AuthenticationRequestTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the request path, not just the auth-permission predicate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    async def test_basic_retry_requires_verified_https_or_explicit_opt_in(self) -> None:
        for protocol, verify_ssl, opt_in in product(
            ("http", "https"), (False, True), (False, True)
        ):
            retry = (protocol == "https" and verify_ssl) or opt_in
            with self.subTest(protocol=protocol, verify_ssl=verify_ssl, opt_in=opt_in):
                calls = []
                rejected = SimpleNamespace(
                    status=401, headers={"WWW-Authenticate": "Basic realm=device"}
                )
                accepted = SimpleNamespace(status=200, headers={})

                @asynccontextmanager
                async def request(method, url, **kwargs):
                    calls.append((method, url, kwargs))
                    yield accepted if "auth" in kwargs else rejected

                api = self.api_module.TwoNIntercomAPI(
                    host="intercom.local", username="api-user", password="test-secret",
                    port=443 if protocol == "https" else 80,
                    protocol=protocol, verify_ssl=verify_ssl, allow_insecure=opt_in,
                    session=SimpleNamespace(closed=False, request=request),
                )
                if not retry:
                    with self.assertLogs(self.api_module._LOGGER, level="WARNING") as logs:
                        with self.assertRaises(
                            self.api_module.TwoNInsecureAuthRefusedError
                        ) as ctx:
                            async with api._async_request("GET", "/api/system/info"):
                                self.fail("A refused response must not be yielded")
                    self.assertIsInstance(ctx.exception, self.api_module.TwoNAuthenticationError)
                    self.assertEqual(len(logs.output), 1)
                    message = logs.output[0]
                    for expected in (
                        "without verified HTTPS", "refusing", "intercom.local",
                        f"protocol={protocol}", f"verify_ssl={verify_ssl}",
                    ):
                        self.assertIn(expected, message)
                    for secret in ("api-user", "test-secret", "Authorization", "BasicAuth"):
                        self.assertNotIn(secret, message)
                else:
                    async with api._async_request("GET", "/api/system/info") as response:
                        self.assertIs(response, accepted)
                self.assertNotIn("auth", calls[0][2])
                self.assertEqual(len(calls), 2 if retry else 1)
                if retry:
                    self.assertEqual(calls[1][2]["auth"].login, "api-user")
                    self.assertEqual(calls[1][2]["auth"].password, "test-secret")

    async def test_digest_path_is_unaffected_for_every_transport_combination(self) -> None:
        for protocol, verify_ssl, opt_in, status in product(
            ("http", "https"), (False, True), (False, True), (200, 401)
        ):
            with self.subTest(
                protocol=protocol, verify_ssl=verify_ssl, opt_in=opt_in, status=status
            ):
                calls = []
                response = SimpleNamespace(
                    status=status, headers={"WWW-Authenticate": "Digest realm=device"}
                )

                @asynccontextmanager
                async def request(method, url, **kwargs):
                    calls.append(kwargs)
                    yield response

                api = self.api_module.TwoNIntercomAPI(
                    host="intercom.local", username="api-user", password="test-secret",
                    protocol=protocol, verify_ssl=verify_ssl, allow_insecure=opt_in,
                )
                with patch.object(self.api_module.aiohttp, "DigestAuthMiddleware") as digest:
                    session = await api.async_get_session()
                    digest.assert_called_once_with(
                        "api-user", "test-secret", preemptive=False
                    )
                session.request = request
                with patch.object(self.api_module._LOGGER, "warning") as warning:
                    async with api._async_request("GET", "/api/call/status") as result:
                        self.assertIs(result, response)
                    warning.assert_not_called()
                self.assertEqual(calls, [{}])
                await api.async_close()

    async def test_connection_test_propagates_insecure_auth_refusal(self) -> None:
        calls = []

        @asynccontextmanager
        async def request(method, url, **kwargs):
            calls.append(kwargs)
            yield SimpleNamespace(
                status=401, headers={"WWW-Authenticate": "Basic realm=device"}
            )

        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="api-user", password="test-secret",
            protocol="https", verify_ssl=False,
            session=SimpleNamespace(closed=False, request=request),
        )
        with self.assertLogs(self.api_module._LOGGER, level="WARNING") as logs:
            with self.assertRaises(self.api_module.TwoNInsecureAuthRefusedError):
                await api.async_test_connection()
        self.assertEqual(calls, [{}])
        self.assertEqual(len(logs.output), 1)


class SessionOwnershipTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the inject-websession session-ownership contract.

    When a caller injects a session via ``__init__``, the API must never
    close it (HA manages its lifecycle). When no session is injected, the
    API creates and owns its own session and is responsible for cleanup.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def test_injected_session_sets_owns_session_false(self) -> None:
        import aiohttp

        external_session = aiohttp.ClientSession()
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
            session=external_session,
        )
        self.assertFalse(api._owns_session)
        self.assertIs(api._session, external_session)

    def test_no_session_sets_owns_session_true(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
        )
        self.assertTrue(api._owns_session)
        self.assertIsNone(api._session)

    async def test_async_close_skips_injected_session(self) -> None:
        import aiohttp

        external_session = aiohttp.ClientSession()
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
            session=external_session,
        )

        await api.async_close()

        # The injected session must NOT be closed by the API
        self.assertFalse(external_session.closed)

    async def test_async_close_closes_self_created_session(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
        )

        # Force the API to create its own session
        session = await api.async_get_session()
        self.assertTrue(api._owns_session)

        await api.async_close()

        self.assertTrue(session.closed)
        self.assertIsNone(api._session)

    async def test_async_get_session_fallback_marks_owned(self) -> None:
        """When no session was injected and async_get_session creates one,
        the new session must be marked as owned so async_close cleans it up."""
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
        )

        session = await api.async_get_session()

        self.assertIsNotNone(session)
        self.assertTrue(api._owns_session)

    async def test_reset_preserves_shared_connector_and_uses_factory(self) -> None:
        aiohttp = self.api_module.aiohttp
        connector = aiohttp.TCPConnector(ssl=False)
        unrelated_session = aiohttp.ClientSession(connector=connector)
        sessions = []

        def create_session():
            session = aiohttp.ClientSession(connector=connector)
            sessions.append(session)
            return session

        api = self.api_module.TwoNIntercomAPI(
            "intercom.local", "user", "secret",
            session=create_session(), session_factory=create_session,
        )

        for _ in range(3):
            old_session = await api.async_get_session()
            await api.async_reset_session()
            self.assertTrue(old_session.closed)
            self.assertFalse(connector.closed)
            self.assertFalse(unrelated_session.closed)
            self.assertIsNone(api._session)

            replacement = await api.async_get_session()
            self.assertIsNot(replacement, old_session)
            self.assertIs(replacement.connector, connector)
            self.assertFalse(api._owns_session)

        self.assertEqual(len(sessions), 4)

    async def test_reset_closes_owned_connector_and_recreates_session(self) -> None:
        api = self.api_module.TwoNIntercomAPI("intercom.local", "user", "secret")
        old_session = await api.async_get_session()
        old_connector = old_session.connector

        await api.async_reset_session()

        self.assertTrue(old_connector.closed)
        self.assertTrue(old_session.closed)
        replacement = await api.async_get_session()
        self.assertIsNot(replacement, old_session)
        self.assertTrue(api._owns_session)
        await api.async_close()
        self.assertTrue(replacement.closed)

    async def test_closed_injected_session_is_replaced_by_factory(self) -> None:
        aiohttp = self.api_module.aiohttp
        old_session = aiohttp.ClientSession()
        replacement = aiohttp.ClientSession()
        api = self.api_module.TwoNIntercomAPI(
            "intercom.local", "user", "secret",
            session=old_session, session_factory=lambda: replacement,
        )
        old_session.detach()

        self.assertIs(await api.async_get_session(), replacement)
        self.assertFalse(api._owns_session)

    async def test_reset_is_safe_without_an_open_session(self) -> None:
        api = self.api_module.TwoNIntercomAPI("intercom.local", "user", "secret")
        await api.async_reset_session()
        self.assertIsNone(api._session)

        session = await api.async_get_session()
        await session.close()
        await api.async_reset_session()
        await api.async_reset_session()
        self.assertIsNone(api._session)

    async def test_session_factory_failure_is_not_silenced(self) -> None:
        def create_session():
            raise RuntimeError("session creation failed")

        api = self.api_module.TwoNIntercomAPI(
            "intercom.local", "user", "secret", session_factory=create_session,
        )
        with self.assertRaisesRegex(RuntimeError, "session creation failed"):
            await api.async_get_session()
        self.assertIsNone(api._session)


class PureHelperTests(unittest.TestCase):
    """Tests for pure helper functions in api.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def test_unique_in_order(self) -> None:
        fn = self.api_module._unique_in_order
        self.assertEqual(fn(["a", "b", "a", "c"]), ("a", "b", "c"))
        self.assertEqual(fn(["  a ", "a"]), ("a",))
        self.assertEqual(fn([" ", "", "x"]), ("x",))
        self.assertEqual(fn([]), ())

    def test_coerce_int(self) -> None:
        fn = self.api_module._coerce_int
        self.assertEqual(fn(42), 42)
        self.assertEqual(fn("42"), 42)
        self.assertIsNone(fn("abc"))
        self.assertIsNone(fn(True))
        self.assertIsNone(fn(None))
        self.assertIsNone(fn(3.14))

    def test_parse_resolution_string(self) -> None:
        fn = self.api_module._parse_resolution_string
        res = fn("640x480")
        self.assertIsNotNone(res)
        self.assertEqual(res.as_tuple(), (640, 480))
        self.assertIsNone(fn("invalid"))
        self.assertIsNone(fn(""))

    def test_camera_resolution_as_string(self) -> None:
        res = self.api_module.CameraResolution(width=1280, height=960)
        self.assertEqual(res.as_string(), "1280x960")

    def test_collect_camera_sources_string(self) -> None:
        fn = self.api_module._collect_camera_sources
        self.assertEqual(fn("internal"), ["internal"])
        self.assertEqual(fn("  "), [])

    def test_collect_camera_sources_list(self) -> None:
        fn = self.api_module._collect_camera_sources
        self.assertEqual(fn(["internal", "external"]), ["internal", "external"])

    def test_collect_camera_sources_dict(self) -> None:
        fn = self.api_module._collect_camera_sources
        result = fn({"available": ["internal", "external"]})
        self.assertIn("internal", result)
        self.assertIn("external", result)

    def test_collect_camera_sources_nested_dict_key(self) -> None:
        fn = self.api_module._collect_camera_sources
        # A dict child whose key isn't a source/metadata key gets the key itself added
        result = fn({"mycam": {"resolution": "640x480"}})
        self.assertIn("mycam", result)

    def test_collect_camera_sources_dict_string_child(self) -> None:
        fn = self.api_module._collect_camera_sources
        result = fn({"key": "value"})
        self.assertIn("value", result)

    def test_camera_capabilities_preferred_source(self) -> None:
        CameraCapabilities = self.api_module.CameraCapabilities
        self.assertEqual(CameraCapabilities().preferred_source(), "internal")
        self.assertEqual(
            CameraCapabilities(sources=("external", "internal")).preferred_source(),
            "external",
        )

    def test_select_mjpeg_resolution_exact_match(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        CameraCapabilities = self.api_module.CameraCapabilities
        caps = CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(640, 480),
                CameraResolution(1280, 960),
            )
        )
        result = self.api_module.TwoNIntercomAPI._select_mjpeg_resolution(
            caps, width=640, height=480
        )
        self.assertEqual(result, (640, 480))

    def test_select_mjpeg_resolution_fallback_to_largest(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        CameraCapabilities = self.api_module.CameraCapabilities
        caps = CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(320, 240),
                CameraResolution(640, 480),
            )
        )
        result = self.api_module.TwoNIntercomAPI._select_mjpeg_resolution(
            caps, width=1280, height=960
        )
        self.assertEqual(result, (640, 480))

    def test_select_mjpeg_resolution_no_caps(self) -> None:
        CameraCapabilities = self.api_module.CameraCapabilities
        result = self.api_module.TwoNIntercomAPI._select_mjpeg_resolution(
            CameraCapabilities(), width=1280, height=960
        )
        self.assertEqual(result, (1280, 960))

    def test_select_snapshot_resolution_exact_match(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(1280, 960),
                CameraResolution(320, 240),
                CameraResolution(640, 480),
            )
        )
        result = self.api_module.TwoNIntercomAPI._select_snapshot_resolution(
            caps, width=640, height=480
        )
        self.assertEqual(result, (640, 480))

    def test_select_snapshot_resolution_nearest_larger(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(1280, 960),
                CameraResolution(320, 240),
                CameraResolution(640, 480),
            )
        )
        for wanted, expected in (
            ((436, 246), (640, 480)),
            ((436, 236), (640, 480)),
            ((80, 80), (320, 240)),
            ((872, 491), (1280, 960)),
        ):
            with self.subTest(wanted=wanted):
                result = self.api_module.TwoNIntercomAPI._select_snapshot_resolution(
                    caps, width=wanted[0], height=wanted[1]
                )
                self.assertEqual(result, expected)

    def test_select_snapshot_resolution_requires_both_dimensions(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(1280, 240),
                CameraResolution(640, 960),
                CameraResolution(800, 600),
            )
        )
        result = self.api_module.TwoNIntercomAPI._select_snapshot_resolution(
            caps, width=700, height=400
        )
        self.assertEqual(result, (800, 600))

    def test_select_snapshot_resolution_orders_by_area_then_dimensions(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(800, 600),
                CameraResolution(960, 320),
                CameraResolution(640, 480),
            )
        )
        for wanted, expected in (
            ((400, 300), (640, 480)),
            ((2000, 2000), (800, 600)),
        ):
            with self.subTest(wanted=wanted):
                result = self.api_module.TwoNIntercomAPI._select_snapshot_resolution(
                    caps, width=wanted[0], height=wanted[1]
                )
                self.assertEqual(result, expected)

    def test_select_snapshot_resolution_fallback_to_largest(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        for sizes, wanted, expected in (
            (((640, 480), (320, 240)), (872, 491), (640, 480)),
            (((1280, 960), (320, 240), (640, 480)), (2000, 2000), (1280, 960)),
            (((960, 320), (640, 480)), (2000, 2000), (960, 320)),
        ):
            with self.subTest(sizes=sizes, wanted=wanted):
                caps = self.api_module.CameraCapabilities(
                    jpeg_resolutions=tuple(CameraResolution(*size) for size in sizes)
                )
                result = self.api_module.TwoNIntercomAPI._select_snapshot_resolution(
                    caps, width=wanted[0], height=wanted[1]
                )
                self.assertEqual(result, expected)

    def test_select_snapshot_resolution_no_caps(self) -> None:
        result = self.api_module.TwoNIntercomAPI._select_snapshot_resolution(
            self.api_module.CameraCapabilities(), width=1280, height=960
        )
        self.assertIsNone(result)

    def test_requires_basic_auth(self) -> None:
        import types as t

        fn = self.api_module.TwoNIntercomAPI._requires_basic_auth
        basic_401 = t.SimpleNamespace(
            status=401, headers={"WWW-Authenticate": "Basic realm=device"}
        )
        self.assertTrue(fn(basic_401))

        digest_401 = t.SimpleNamespace(
            status=401, headers={"WWW-Authenticate": "Digest realm=device"}
        )
        self.assertFalse(fn(digest_401))

        ok_200 = t.SimpleNamespace(status=200, headers={})
        self.assertFalse(fn(ok_200))

    def test_basic_auth_permitted_over_https(self) -> None:
        """Basic fallback requires a verified HTTPS server."""
        api = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=443, protocol="https",
            verify_ssl=True,
        )
        self.assertTrue(api._basic_auth_permitted())

    def test_basic_auth_refused_over_unverified_https(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=443, protocol="https",
            verify_ssl=False,
        )
        self.assertFalse(api._basic_auth_permitted())

    def test_basic_auth_refused_over_plaintext_http(self) -> None:
        """Basic fallback is refused over plain HTTP unless explicitly allowed."""
        api = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=80, protocol="http",
        )
        self.assertFalse(api._basic_auth_permitted())

    def test_basic_auth_opt_in_over_http(self) -> None:
        """allow_insecure re-enables Basic over HTTP for users who accept the risk."""
        api = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=80, protocol="http",
            allow_insecure=True,
        )
        self.assertTrue(api._basic_auth_permitted())

    def test_build_http_url_with_auth(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user@example.com",
            password="p@ss",
            port=443,
            protocol="https",
        )
        url = api._build_http_url("/api/test", include_auth=True)
        self.assertIn("user%40example.com", url)
        self.assertIn("p%40ss", url)

    def test_get_rtsp_port(self) -> None:
        api443 = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=443
        )
        self.assertEqual(api443._get_rtsp_port(), 554)

        api80 = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=80
        )
        self.assertEqual(api80._get_rtsp_port(), 554)

        api8443 = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p", port=8443
        )
        self.assertEqual(api8443._get_rtsp_port(), 8443)

    def test_get_rtsp_url(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="user", password="secret", port=443,
            rtsp_username="rtspuser", rtsp_password="rtspsecret",
        )
        url = api.get_rtsp_url()
        self.assertEqual(url, "rtsp://rtspuser:****@intercom.local:554/h264_stream")

    def test_get_rtsp_url_no_rtsp_credentials(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="user", password="secret", port=443,
        )
        url = api.get_rtsp_url()
        self.assertIn("rtsp://", url)

    def test_get_rtsp_url_with_credentials(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="user", password="secret", port=443,
            rtsp_username="rtspuser", rtsp_password="rtspsecret",
        )
        url = api.get_rtsp_url_with_credentials()
        self.assertEqual(
            url, "rtsp://rtspuser:rtspsecret@intercom.local:554/h264_stream"
        )

    def test_get_rtsp_url_with_credentials_none_without_rtsp_creds(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="user", password="secret", port=443,
        )
        self.assertIsNone(api.get_rtsp_url_with_credentials())

    def test_get_rtsp_url_with_credentials_url_encodes_special_chars(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="user", password="secret", port=443,
            rtsp_username="user@2n", rtsp_password="p@ss!word",
        )
        url = api.get_rtsp_url_with_credentials()
        self.assertIn("user%402n", url)
        self.assertIn("p%40ss%21word", url)

    def test_build_snapshot_url(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local", username="u", password="p", port=443
        )
        url = api.build_snapshot_url(width=640, height=480, source="internal")
        self.assertIn("/api/camera/snapshot", url)
        self.assertIn("width=640", url)
        self.assertNotIn("fps=", url)

    def test_camera_transport_properties(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="x", username="u", password="p"
        )
        self.assertIsInstance(api.camera_capabilities, self.api_module.CameraCapabilities)
        self.assertIsInstance(api.camera_transport_info, self.api_module.CameraTransportInfo)
        self.assertFalse(api.camera_transport_resolved)

    def test_parse_camera_caps_none(self) -> None:
        self.assertEqual(
            self.api_module.parse_camera_caps(None),
            self.api_module.CameraCapabilities(),
        )

    def test_validate_mjpeg_fps_valid(self) -> None:
        self.assertEqual(self.api_module.validate_mjpeg_fps(1), 1)
        self.assertEqual(self.api_module.validate_mjpeg_fps(15), 15)

    def test_select_live_view_mode_requested_rtsp(self) -> None:
        fn = self.api_module.select_live_view_mode
        # User requests rtsp, it's available → rtsp
        self.assertEqual(
            fn(rtsp_available=True, mjpeg_available=True, requested_mode="rtsp"),
            "rtsp",
        )
        # User requests rtsp, not available → fallback to mjpeg
        self.assertEqual(
            fn(rtsp_available=False, mjpeg_available=True, requested_mode="rtsp"),
            "mjpeg",
        )

    def test_select_live_view_mode_requested_mjpeg(self) -> None:
        fn = self.api_module.select_live_view_mode
        self.assertEqual(
            fn(rtsp_available=True, mjpeg_available=True, requested_mode="mjpeg"),
            "mjpeg",
        )


class AdditionalApiMethodTests(unittest.IsolatedAsyncioTestCase):
    """Tests for API methods not covered by CallControlApiTests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def _make_api(self, response_payload=None, status=200, content_type="application/json"):
        api_module = self.api_module

        class FakeResponse:
            def __init__(self, payload, status_, ct):
                self.status = status_
                self.headers = {"Content-Type": ct}
                self._payload = payload or {"success": True}
                self._body = b""

            async def json(self):
                return self._payload

            async def text(self):
                import json as j
                return j.dumps(self._payload)

            async def read(self):
                return self._body

            def raise_for_status(self):
                return None

        class TestApi(api_module.TwoNIntercomAPI):
            def __init__(self, payload, status_, ct):
                super().__init__(
                    host="intercom.local", username="user", password="secret",
                    port=443, protocol="https",
                )
                self.requests = []
                self.response = FakeResponse(payload, status_, ct)

            @asynccontextmanager
            async def _async_request(self, method, path, *, params=None, json_data=None, headers=None):
                self.requests.append({
                    "method": method, "path": path, "params": params, "json_data": json_data,
                })
                yield self.response

        return TestApi(response_payload, status, content_type)

    def _make_snapshot_api(self, *snapshot_responses, capabilities=None, caps_payload=None):
        """Exercise snapshot HTTP requests through a fake injected session."""
        api_module = self.api_module

        class FakeResponse:
            status = 200

            def __init__(self, payload):
                self._payload = payload
                self.headers = {
                    "Content-Type": (
                        "image/jpeg" if isinstance(payload, bytes) else "application/json"
                    )
                }

            async def json(self):
                return self._payload

            async def text(self):
                return json.dumps(self._payload)

            async def read(self):
                return self._payload

            def raise_for_status(self):
                return None

        class FakeSession(api_module.aiohttp.ClientSession):
            def __init__(self):
                super().__init__()
                self.requests = []

            @property
            def snapshot_requests(self):
                return [
                    request for request in self.requests
                    if request["url"].endswith("/api/camera/snapshot")
                ]

            @asynccontextmanager
            async def request(self, method, url, **kwargs):
                self.requests.append({"method": method, "url": url, **kwargs})
                if url.endswith("/api/camera/caps"):
                    yield FakeResponse(
                        caps_payload if caps_payload is not None
                        else {"success": True, "result": {}}
                    )
                else:
                    index = min(len(self.snapshot_requests), len(snapshot_responses)) - 1
                    yield FakeResponse(snapshot_responses[index])

        session = FakeSession()
        api = api_module.TwoNIntercomAPI(
            host="intercom.local", username="user", password="secret", session=session
        )
        if capabilities is not None:
            api._camera_capabilities = capabilities
        return api, session

    async def test_get_system_info_success(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {"serialNumber": "SN123", "variant": "IP Verso"},
        })
        result = await api.async_get_system_info()
        self.assertEqual(result, {"serialNumber": "SN123", "variant": "IP Verso"})

    async def test_get_system_info_failure(self) -> None:
        api = self._make_api({"success": False, "error": {"code": 8, "description": "auth"}})
        result = await api.async_get_system_info()
        self.assertEqual(result, {})

    async def test_get_call_status_success(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {"state": "idle", "sessions": []},
        })
        result = await api.async_get_call_status()
        self.assertEqual(result, {"state": "idle", "sessions": []})

    async def test_get_call_status_failure(self) -> None:
        api = self._make_api({"success": False, "error": {"code": 8, "description": "auth"}})
        result = await api.async_get_call_status()
        self.assertEqual(result, {})

    async def test_get_result_dict_non_dict_result(self) -> None:
        api = self._make_api({"success": True, "result": "not_a_dict"})
        result = await api._async_get_result_dict("/api/test", "test")
        self.assertEqual(result, {})

    async def test_async_connect_success(self) -> None:
        api = self._make_api({"success": True, "result": {}})
        result = await api.async_connect()
        self.assertTrue(result)

    async def test_async_connect_failure(self) -> None:
        api = self._make_api()

        async def fail(*args, **kwargs):
            raise RuntimeError("nope")

        # Override _async_request to fail
        orig = api._async_request
        @asynccontextmanager
        async def failing_request(*args, **kwargs):
            raise RuntimeError("nope")
        api._async_request = failing_request
        result = await api.async_connect()
        self.assertFalse(result)

    async def test_async_test_connection_success(self) -> None:
        api = self._make_api({"success": True, "result": {}})
        result = await api.async_test_connection()
        self.assertTrue(result)

    async def test_async_test_connection_failure(self) -> None:
        api = self._make_api()

        @asynccontextmanager
        async def failing_request(*args, **kwargs):
            raise RuntimeError("nope")
        api._async_request = failing_request
        result = await api.async_test_connection()
        self.assertFalse(result)

    async def test_async_reconnect(self) -> None:
        api = self._make_api({"success": True, "result": {}})
        result = await api.async_reconnect()
        self.assertTrue(result)

    async def test_get_directory_success(self) -> None:
        api = self._make_api({
            "success": True,
            "result": [{"name": "John"}],
        })
        result = await api.async_get_directory()
        self.assertEqual(result, [{"name": "John"}])
        self.assertEqual(api.requests[0]["method"], "POST")
        self.assertEqual(api.requests[0]["path"], "/api/dir/query")
        self.assertEqual(api.requests[0]["json_data"], {
            "iterator": {"timestamp": 0},
            "fields": ["name", "callPos.peer"],
        })

    async def test_get_directory_users_keeps_uuid_metadata_with_field_selection(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {
                "series": "1",
                "users": [{"uuid": "USER-1", "name": "Alice", "timestamp": 1}],
            },
        })
        users = await api.async_get_directory_users()
        self.assertEqual(users, [{"uuid": "USER-1", "name": "Alice"}])
        self.assertEqual(
            api.requests[0]["json_data"]["fields"], ["name", "callPos.peer"]
        )

    async def test_get_directory_failure(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 8, "description": "auth"},
        })
        result = await api.async_get_directory()
        self.assertEqual(result, [])

    async def test_get_directory_raises_device_errors_only_when_requested(self) -> None:
        for payload in (
            {"success": False, "error": {"code": 10, "description": "insufficient privileges"}},
            {"success": False},
        ):
            with self.subTest(payload=payload):
                api = self._make_api(payload)
                with self.assertNoLogs(self.api_module._LOGGER, "WARNING"):
                    with self.assertRaises(self.api_module.TwoNAPIError):
                        await api.async_get_directory(raise_on_device_error=True)

    async def test_get_directory_legacy_users_format(self) -> None:
        api = self._make_api({"users": [{"name": "Jane"}]})
        result = await api.async_get_directory()
        self.assertEqual(result, [{"name": "Jane"}])

    async def test_subscribe_log_empty_filter(self) -> None:
        api = self._make_api()
        result = await api.async_subscribe_log([])
        self.assertIsNone(result)

    async def test_subscribe_log_failure(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 8, "description": "auth"},
        })
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertIsNone(result)

    async def test_subscribe_log_non_dict_result(self) -> None:
        api = self._make_api({"success": True, "result": "bad"})
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertIsNone(result)

    async def test_subscribe_log_string_id(self) -> None:
        api = self._make_api({"success": True, "result": {"id": "123"}})
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertEqual(result, 123)

    async def test_pull_log_failure(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 8, "description": "auth"},
        })
        result = await api.async_pull_log(99)
        self.assertEqual(result, [])

    async def test_pull_log_non_dict(self) -> None:
        api = self._make_api("not a dict")
        result = await api.async_pull_log(99)
        self.assertEqual(result, [])

    async def test_pull_log_non_dict_result(self) -> None:
        api = self._make_api({"success": True, "result": "bad"})
        result = await api.async_pull_log(99)
        self.assertEqual(result, [])

    async def test_pull_log_filters_non_dict_events(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {"events": [{"event": "ok"}, "bad"]},
        })
        result = await api.async_pull_log(99)
        self.assertEqual(result, [{"event": "ok"}])

    async def test_unsubscribe_log_failure(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 14, "description": "not found"},
        })
        result = await api.async_unsubscribe_log(99)
        self.assertFalse(result)

    async def test_get_camera_caps_success(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {
                "jpeg": {"resolutions": ["640x480"]},
                "sources": {"available": ["internal"]},
            },
        })
        caps = await api.async_get_camera_caps()
        self.assertEqual(len(caps.jpeg_resolutions), 1)

    async def test_get_camera_caps_cached(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        CameraCapabilities = self.api_module.CameraCapabilities
        api = self._make_api()
        api._camera_capabilities = CameraCapabilities(
            jpeg_resolutions=(CameraResolution(640, 480),)
        )
        caps = await api.async_get_camera_caps()
        self.assertEqual(len(caps.jpeg_resolutions), 1)
        # Should not have made a request (cached)
        self.assertEqual(len(api.requests), 0)

    async def test_get_camera_caps_failure(self) -> None:
        api = self._make_api()

        @asynccontextmanager
        async def failing_request(*args, **kwargs):
            raise RuntimeError("fail")
        api._async_request = failing_request
        caps = await api.async_get_camera_caps()
        self.assertEqual(caps, self.api_module.CameraCapabilities())

    async def test_get_snapshot_success(self) -> None:
        api = self._make_api(None, content_type="image/jpeg")
        api.response._body = b"\xff\xd8\xff"
        result = await api.async_get_snapshot(640, 480)
        self.assertEqual(result, b"\xff\xd8\xff")

    async def test_get_snapshot_non_image_with_code12_retry(self) -> None:
        """Snapshot rejected with code 12 at non-standard size retries at 640x480."""
        api, session = self._make_snapshot_api(
            {"success": False, "error": {"code": 12, "description": "bad size"}},
            b"\xff\xd8\xff",
        )
        with self.assertLogs(self.api_module._LOGGER, level="DEBUG") as logs:
            result = await api.async_get_snapshot(80, 80)

        self.assertEqual(result, b"\xff\xd8\xff")
        self.assertEqual(
            [request["params"] for request in session.snapshot_requests],
            [
                {"source": "internal", "width": 80, "height": 80},
                {"source": "internal", "width": 640, "height": 480},
            ],
        )
        self.assertEqual(
            sum("retrying at 640x480" in message for message in logs.output), 1
        )

    async def test_get_snapshot_maps_to_cached_caps_with_one_http_request(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(640, 480),
                CameraResolution(1280, 960),
            )
        )
        api, session = self._make_snapshot_api(b"\xff\xd8\xff", capabilities=caps)

        result = await api.async_get_snapshot(872, 491)

        self.assertEqual(result, b"\xff\xd8\xff")
        self.assertEqual(len(session.requests), 1)
        request = session.requests[0]
        self.assertEqual(request["method"], "GET")
        self.assertTrue(request["url"].endswith("/api/camera/snapshot"))
        self.assertEqual(
            request["params"], {"source": "internal", "width": 1280, "height": 960}
        )
        self.assertEqual(request["headers"], {"Accept": "image/jpeg"})

    async def test_get_snapshot_fetches_and_caches_caps_before_mapping(self) -> None:
        api, session = self._make_snapshot_api(
            b"\xff\xd8\xff",
            caps_payload={
                "success": True,
                "result": {"jpeg": {"resolutions": ["320x240", "640x480", "1280x960"]}},
            },
        )

        for _ in range(2):
            self.assertEqual(await api.async_get_snapshot(436, 246), b"\xff\xd8\xff")

        self.assertEqual(
            [request["url"].rsplit("/", 1)[-1] for request in session.requests],
            ["caps", "snapshot", "snapshot"],
        )
        self.assertEqual(
            [request["params"] for request in session.snapshot_requests],
            [{"source": "internal", "width": 640, "height": 480}] * 2,
        )

    async def test_get_snapshot_without_caps_logs_fallback_once(self) -> None:
        api, session = self._make_snapshot_api(b"\xff\xd8\xff")

        with self.assertLogs(self.api_module._LOGGER, level="DEBUG") as logs:
            for _ in range(2):
                self.assertEqual(await api.async_get_snapshot(436, 246), b"\xff\xd8\xff")

        self.assertEqual(
            [request["params"] for request in session.snapshot_requests],
            [{"source": "internal", "width": 436, "height": 246}] * 2,
        )
        fallback_logs = [
            record for record in logs.records
            if record.getMessage() == (
                "camera/caps has no JPEG resolutions; snapshot uses requested "
                "size with 640x480 fallback"
            )
        ]
        self.assertEqual(len(fallback_logs), 1)
        self.assertEqual(fallback_logs[0].levelno, logging.DEBUG)

    async def test_get_snapshot_code12_retry_bypasses_caps_and_stops(self) -> None:
        CameraResolution = self.api_module.CameraResolution
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(
                CameraResolution(1280, 720),
                CameraResolution(1920, 1080),
            )
        )
        api, session = self._make_snapshot_api(
            {
                "success": False,
                "error": {
                    "code": 12,
                    "description": "invalid image resolution",
                    "param": "width or height",
                },
            },
            capabilities=caps,
        )

        with self.assertLogs(self.api_module._LOGGER, level="DEBUG") as logs:
            result = await api.async_get_snapshot(872, 491, source=" external ")

        self.assertIsNone(result)
        self.assertEqual(len(session.requests), 2)
        self.assertEqual(
            [request["params"] for request in session.requests],
            [
                {"source": "external", "width": 1280, "height": 720},
                {"source": "external", "width": 640, "height": 480},
            ],
        )
        self.assertEqual(
            [record.levelno for record in logs.records], [logging.DEBUG, logging.WARNING]
        )
        self.assertIn("retrying at 640x480", logs.records[0].getMessage())
        self.assertIn("code=12", logs.records[1].getMessage())

    async def test_get_snapshot_code12_retry_without_caps_stops(self) -> None:
        api, session = self._make_snapshot_api(
            {"success": False, "error": {"code": 12, "description": "bad size"}}
        )

        with self.assertLogs(self.api_module._LOGGER, level="WARNING") as logs:
            result = await api.async_get_snapshot(80, 80)

        self.assertIsNone(result)
        self.assertEqual(
            [request["params"] for request in session.snapshot_requests],
            [
                {"source": "internal", "width": 80, "height": 80},
                {"source": "internal", "width": 640, "height": 480},
            ],
        )
        self.assertEqual([record.levelno for record in logs.records], [logging.WARNING])
        self.assertIn("code=12", logs.output[0])

    async def test_get_snapshot_code12_at_640x480_does_not_retry(self) -> None:
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(self.api_module.CameraResolution(640, 480),)
        )
        api, session = self._make_snapshot_api(
            {"success": False, "error": {"code": 12, "description": "bad size"}},
            capabilities=caps,
        )

        with self.assertLogs(self.api_module._LOGGER, level="WARNING"):
            result = await api.async_get_snapshot()

        self.assertIsNone(result)
        self.assertEqual(len(session.requests), 1)
        self.assertEqual(
            session.requests[0]["params"],
            {"source": "internal", "width": 640, "height": 480},
        )

    async def test_get_snapshot_maps_default_dimensions_and_normalizes_source(self) -> None:
        caps = self.api_module.CameraCapabilities(
            jpeg_resolutions=(self.api_module.CameraResolution(1280, 720),)
        )
        for source, expected_source in (
            (None, "internal"),
            ("   ", "internal"),
            (" external ", "external"),
        ):
            with self.subTest(source=source):
                api, session = self._make_snapshot_api(b"\xff", capabilities=caps)
                self.assertEqual(await api.async_get_snapshot(source=source), b"\xff")
                self.assertEqual(len(session.requests), 1)
                self.assertEqual(
                    session.requests[0]["params"],
                    {"source": expected_source, "width": 1280, "height": 720},
                )

    async def test_get_snapshot_non_image_other_error(self) -> None:
        api = self._make_api(
            {"success": False, "error": {"code": 8, "description": "auth failed"}},
            content_type="application/json",
        )
        result = await api.async_get_snapshot(640, 480)
        self.assertIsNone(result)

    async def test_get_snapshot_non_image_no_device_error(self) -> None:
        api = self._make_api(None, content_type="text/html")
        api.response._payload = None
        result = await api.async_get_snapshot()
        self.assertIsNone(result)

    async def test_switch_control_with_duration(self) -> None:
        api = self._make_api({"success": True})
        result = await api.async_switch_control(relay=1, action="trigger", duration=2000)
        self.assertTrue(result)
        self.assertIn("duration", api.requests[0]["params"])

    async def test_subscribe_log_non_dict_payload(self) -> None:
        api = self._make_api()
        api.response._payload = "not_a_dict"
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertIsNone(result)

    async def test_camera_transport_info_cached(self) -> None:
        """Transport info is cached when already resolved."""
        api_module = self.api_module

        class CachingApi(api_module.TwoNIntercomAPI):
            def __init__(self):
                super().__init__(host="x", username="u", password="p")
                self.probe_count = 0

            async def async_get_camera_caps(self, *, force_refresh=False):
                return api_module.CameraCapabilities()

            async def async_probe_rtsp(self):
                self.probe_count += 1
                return False

            async def async_probe_mjpeg(self, **kwargs):
                return False

            async def async_probe_mjpeg_public(self, **kwargs):
                return False

        api = CachingApi()
        await api.async_get_camera_transport_info()
        await api.async_get_camera_transport_info()
        self.assertEqual(api.probe_count, 1)  # only probed once

    async def test_camera_transport_with_requested_source(self) -> None:
        api_module = self.api_module

        class SourceApi(api_module.TwoNIntercomAPI):
            async def async_get_camera_caps(self, *, force_refresh=False):
                return api_module.CameraCapabilities(sources=("internal", "external"))

            async def async_probe_rtsp(self):
                return False

            async def async_probe_mjpeg(self, **kwargs):
                return False

            async def async_probe_mjpeg_public(self, **kwargs):
                return False

        api = SourceApi(host="x", username="u", password="p")
        info = await api.async_get_camera_transport_info(camera_source="external")
        self.assertEqual(info.source, "external")

    async def test_camera_transport_skips_rtsp_probe_when_not_capable(self) -> None:
        """RTSP probe is skipped when rtsp_capable=False from system/caps."""
        api_module = self.api_module

        class ProbeTrackingApi(api_module.TwoNIntercomAPI):
            def __init__(self):
                super().__init__(host="x", username="u", password="p")
                self.rtsp_probe_count = 0

            async def async_get_camera_caps(self, *, force_refresh=False):
                return api_module.CameraCapabilities()

            async def async_probe_rtsp(self):
                self.rtsp_probe_count += 1
                return False

            async def async_probe_mjpeg(self, **kwargs):
                return False

            async def async_probe_mjpeg_public(self, **kwargs):
                return False

        api = ProbeTrackingApi()
        info = await api.async_get_camera_transport_info(rtsp_capable=False)
        self.assertEqual(api.rtsp_probe_count, 0)
        self.assertFalse(info.rtsp_available)

    async def test_camera_transport_probes_rtsp_when_capable(self) -> None:
        """RTSP probe runs normally when rtsp_capable=True."""
        api_module = self.api_module

        class ProbeTrackingApi(api_module.TwoNIntercomAPI):
            def __init__(self):
                super().__init__(host="x", username="u", password="p")
                self.rtsp_probe_count = 0

            async def async_get_camera_caps(self, *, force_refresh=False):
                return api_module.CameraCapabilities()

            async def async_probe_rtsp(self):
                self.rtsp_probe_count += 1
                return False

            async def async_probe_mjpeg(self, **kwargs):
                return False

            async def async_probe_mjpeg_public(self, **kwargs):
                return False

        api = ProbeTrackingApi()
        await api.async_get_camera_transport_info(rtsp_capable=True)
        self.assertEqual(api.rtsp_probe_count, 1)

    async def test_camera_transport_probes_rtsp_when_capable_is_none(self) -> None:
        """RTSP probe runs when rtsp_capable is not passed (backwards compat)."""
        api_module = self.api_module

        class ProbeTrackingApi(api_module.TwoNIntercomAPI):
            def __init__(self):
                super().__init__(host="x", username="u", password="p")
                self.rtsp_probe_count = 0

            async def async_get_camera_caps(self, *, force_refresh=False):
                return api_module.CameraCapabilities()

            async def async_probe_rtsp(self):
                self.rtsp_probe_count += 1
                return False

            async def async_probe_mjpeg(self, **kwargs):
                return False

            async def async_probe_mjpeg_public(self, **kwargs):
                return False

        api = ProbeTrackingApi()
        await api.async_get_camera_transport_info()
        self.assertEqual(api.rtsp_probe_count, 1)

    async def test_get_system_caps_success(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {
                "options": {
                    "motionDetection": "active,licensed",
                    "enhancedVideo": "active,licensed",
                }
            },
        })
        caps = await api.async_get_system_caps()
        self.assertEqual(caps["motionDetection"], "active,licensed")
        self.assertEqual(caps["enhancedVideo"], "active,licensed")

    async def test_get_system_caps_empty_on_failure(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 12, "description": "not supported"},
        })
        caps = await api.async_get_system_caps()
        self.assertEqual(caps, {})

    async def test_get_system_caps_empty_on_exception(self) -> None:
        api = self._make_api()

        async def failing_request(*a, **kw):
            raise RuntimeError("fail")
        api._async_request = failing_request
        caps = await api.async_get_system_caps()
        self.assertEqual(caps, {})


class ExceptionHandlingTests(unittest.IsolatedAsyncioTestCase):
    """Tests for API exception handling branches."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def _make_failing_api(self, exception_cls, message="test error"):
        """Create an API that raises the given exception on requests."""
        api_module = self.api_module

        class FailingApi(api_module.TwoNIntercomAPI):
            def __init__(self, exc_cls, msg):
                super().__init__(host="x", username="u", password="p")
                self._exc_cls = exc_cls
                self._msg = msg

            @asynccontextmanager
            async def _async_request(self, method, path, *, params=None, json_data=None, headers=None):
                raise self._exc_cls(self._msg)
                yield  # pragma: no cover

        return FailingApi(exception_cls, message)

    async def test_get_call_status_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_get_call_status()

    async def test_get_call_status_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_call_status()

    async def test_get_call_status_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_call_status()

    async def test_get_call_status_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        with self.assertRaises(self.api_module.TwoNAPIError):
            await api.async_get_call_status()

    async def test_get_system_info_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_system_info()

    async def test_get_system_info_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_system_info()

    async def test_get_system_info_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        with self.assertRaises(self.api_module.TwoNAPIError):
            await api.async_get_system_info()

    async def test_get_result_dict_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_phone_status()

    async def test_get_result_dict_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_phone_status()

    async def test_get_result_dict_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        with self.assertRaises(self.api_module.TwoNAPIError):
            await api.async_get_phone_status()

    async def test_call_action_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        result = await api.async_answer_call("s1")
        self.assertFalse(result)

    async def test_call_action_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        result = await api.async_answer_call("s1")
        self.assertFalse(result)

    async def test_call_action_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        result = await api.async_answer_call("s1")
        self.assertFalse(result)

    async def test_subscribe_log_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertIsNone(result)

    async def test_subscribe_log_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertIsNone(result)

    async def test_subscribe_log_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        result = await api.async_subscribe_log(["CallStateChanged"])
        self.assertIsNone(result)

    async def test_pull_log_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        result = await api.async_pull_log(99)
        self.assertEqual(result, [])

    async def test_pull_log_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        result = await api.async_pull_log(99)
        self.assertEqual(result, [])

    async def test_pull_log_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        result = await api.async_pull_log(99)
        self.assertEqual(result, [])

    async def test_unsubscribe_log_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        result = await api.async_unsubscribe_log(99)
        self.assertFalse(result)

    async def test_unsubscribe_log_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        result = await api.async_unsubscribe_log(99)
        self.assertFalse(result)

    async def test_unsubscribe_log_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        result = await api.async_unsubscribe_log(99)
        self.assertFalse(result)

    async def test_get_directory_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_get_directory()

    async def test_get_directory_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_directory()

    async def test_get_directory_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        with self.assertRaises(self.api_module.TwoNConnectionError):
            await api.async_get_directory()

    async def test_get_directory_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        with self.assertRaises(self.api_module.TwoNAPIError):
            await api.async_get_directory()

    async def test_switch_control_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        result = await api.async_switch_control(relay=1)
        self.assertFalse(result)

    async def test_switch_control_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        result = await api.async_switch_control(relay=1)
        self.assertFalse(result)

    async def test_switch_control_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        result = await api.async_switch_control(relay=1)
        self.assertFalse(result)

    async def test_get_snapshot_timeout(self) -> None:
        api = self._make_failing_api(TimeoutError)
        result = await api.async_get_snapshot()
        self.assertIsNone(result)

    async def test_get_snapshot_client_error(self) -> None:
        import aiohttp
        api = self._make_failing_api(aiohttp.ClientError)
        result = await api.async_get_snapshot()
        self.assertIsNone(result)

    async def test_get_snapshot_generic_error(self) -> None:
        api = self._make_failing_api(RuntimeError)
        result = await api.async_get_snapshot()
        self.assertIsNone(result)

    async def test_call_action_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_answer_call("s1")

    async def test_subscribe_log_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_subscribe_log(["CallStateChanged"])

    async def test_pull_log_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_pull_log(99)

    async def test_unsubscribe_log_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_unsubscribe_log(99)

    async def test_get_result_dict_auth_error(self) -> None:
        api = self._make_failing_api(self.api_module.TwoNAuthenticationError)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_get_phone_status()


class SelectLiveViewModeEdgeCases(unittest.TestCase):
    """Edge cases for select_live_view_mode."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def test_jpeg_only_requested(self) -> None:
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=True, mjpeg_available=True, requested_mode="jpeg_only"
            ),
            "jpeg_only",
        )

    def test_rtsp_requested_nothing_available(self) -> None:
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=False, mjpeg_available=False, requested_mode="rtsp"
            ),
            "jpeg_only",
        )

    def test_mjpeg_requested_not_available_rtsp_available(self) -> None:
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=True, mjpeg_available=False, requested_mode="mjpeg"
            ),
            "rtsp",
        )

    def test_mjpeg_requested_nothing_available(self) -> None:
        self.assertEqual(
            self.api_module.select_live_view_mode(
                rtsp_available=False, mjpeg_available=False, requested_mode="mjpeg"
            ),
            "jpeg_only",
        )



class AccessControlApiTests(unittest.IsolatedAsyncioTestCase):
    """Tests for log caps, directory users and grant access (TASK-4/TASK-8)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api_module = load_api_module()

    def _make_api(self, response_payload=None, status=200):
        return AdditionalApiMethodTests._make_api(self, response_payload, status)

    # -- /api/log/caps -------------------------------------------------

    async def test_get_log_caps_returns_event_names(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {"events": ["CardEntered", " CodeEntered ", "", 5, "CallStateChanged"]},
        })
        caps = await api.async_get_log_caps()
        self.assertEqual(caps, ["CardEntered", "CodeEntered", "CallStateChanged"])
        self.assertEqual(api.requests[0]["path"], "/api/log/caps")
        self.assertEqual(api.requests[0]["method"], "GET")

    async def test_get_log_caps_device_error_returns_none(self) -> None:
        api = self._make_api({"success": False, "error": {"code": 2, "description": "invalid path"}})
        self.assertIsNone(await api.async_get_log_caps())

    async def test_get_log_caps_without_events_list_returns_none(self) -> None:
        api = self._make_api({"success": True, "result": {"events": "CardEntered"}})
        self.assertIsNone(await api.async_get_log_caps())

    async def test_get_log_caps_auth_failure_raises(self) -> None:
        api = self._make_api({"success": False}, status=401)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_get_log_caps()

    # -- directory users ------------------------------------------------

    def test_extract_directory_users_handles_result_shapes(self) -> None:
        extract = self.api_module.extract_directory_users
        payload = {
            "series": "1",
            "users": [
                {"uuid": "01234567-89AB-CDEF-0123-456789ABCDEF", "name": " Alice "},
                {"uuid": "", "name": "No uuid"},
                {"name": "Missing uuid"},
                "garbage",
                {"uuid": "A6543210-68FF-18CA-3210-FEDCBA987654"},
            ],
        }
        self.assertEqual(
            extract(payload),
            [
                {"uuid": "01234567-89AB-CDEF-0123-456789ABCDEF", "name": "Alice"},
                {"uuid": "A6543210-68FF-18CA-3210-FEDCBA987654", "name": ""},
            ],
        )
        self.assertEqual(extract([{"uuid": "x", "name": "y"}]), [{"uuid": "x", "name": "y"}])
        self.assertEqual(extract(None), [])
        self.assertEqual(extract({"users": "nope"}), [])

    async def test_get_directory_users_queries_dir(self) -> None:
        api = self._make_api({
            "success": True,
            "result": {"series": "1", "users": [{"uuid": "U-1", "name": "Bob"}]},
        })
        users = await api.async_get_directory_users()
        self.assertEqual(users, [{"uuid": "U-1", "name": "Bob"}])
        self.assertEqual(api.requests[0]["path"], "/api/dir/query")

    # -- /api/accesspoint/grantaccess ----------------------------------

    async def test_grant_access_granted(self) -> None:
        api = self._make_api({"success": True, "result": {"accessGranted": True}})
        result = await api.async_grant_access(0, "UUID-1")
        self.assertTrue(result.granted)
        self.assertIsNone(result.reason)
        self.assertEqual(api.requests[0]["method"], "GET")
        self.assertEqual(api.requests[0]["path"], "/api/accesspoint/grantaccess")
        self.assertEqual(api.requests[0]["params"], {"id": 0, "user": "UUID-1"})

    async def test_grant_access_exit_access_point(self) -> None:
        api = self._make_api({"success": True, "result": {"accessGranted": "true"}})
        result = await api.async_grant_access(1, "UUID-1")
        self.assertTrue(result.granted)
        self.assertEqual(api.requests[0]["params"]["id"], 1)

    async def test_grant_access_denied_for_each_documented_reason(self) -> None:
        for reason in ("invalidAp", "invalidCredential", "accessBlocked"):
            api = self._make_api({
                "success": True,
                "result": {"accessGranted": False, "reason": reason},
            })
            with self.assertLogs(self.api_module._LOGGER, level="WARNING"):
                result = await api.async_grant_access(0, "UUID-1")
            self.assertFalse(result.granted)
            self.assertEqual(result.reason, reason)

    async def test_grant_access_missing_granted_flag_raises(self) -> None:
        api = self._make_api({"success": True, "result": {}})
        with self.assertRaises(self.api_module.TwoNAPIError):
            await api.async_grant_access(0, "UUID-1")

    async def test_grant_access_error_code_18_is_rejected(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 18, "description": "request rejected"},
        })
        with self.assertLogs(self.api_module._LOGGER, level="WARNING") as logs:
            with self.assertRaises(self.api_module.TwoNDeviceRejectedError) as ctx:
                await api.async_grant_access(0, "SECRET-UUID")
        self.assertEqual(ctx.exception.kind, "rejected")
        self.assertEqual(ctx.exception.error.code, 18)
        self.assertNotIn("SECRET-UUID", "\n".join(logs.output))

    async def test_grant_access_missing_privilege_is_permission_error(self) -> None:
        for code in (8, 9, 10):
            api = self._make_api({
                "success": False,
                "error": {"code": code, "description": "insufficient privileges"},
            })
            with self.assertLogs(self.api_module._LOGGER, level="WARNING"):
                with self.assertRaises(self.api_module.TwoNDeviceRejectedError) as ctx:
                    await api.async_grant_access(0, "UUID-1")
            self.assertEqual(ctx.exception.kind, "permission")

    async def test_grant_access_http_401_raises_auth_error(self) -> None:
        api = self._make_api({"success": False}, status=401)
        with self.assertRaises(self.api_module.TwoNAuthenticationError):
            await api.async_grant_access(0, "UUID-1")

    async def test_grant_access_unsupported_endpoint(self) -> None:
        api = self._make_api({"success": False}, status=404)
        with self.assertRaises(self.api_module.TwoNDeviceRejectedError) as ctx:
            await api.async_grant_access(0, "UUID-1")
        self.assertEqual(ctx.exception.kind, "unsupported")

        for code in (1, 2, 4):
            api = self._make_api({
                "success": False,
                "error": {"code": code, "description": "not supported"},
            })
            with self.assertLogs(self.api_module._LOGGER, level="WARNING"):
                with self.assertRaises(self.api_module.TwoNDeviceRejectedError) as ctx:
                    await api.async_grant_access(0, "UUID-1")
            self.assertEqual(ctx.exception.kind, "unsupported")

    async def test_grant_access_other_device_error(self) -> None:
        api = self._make_api({
            "success": False,
            "error": {"code": 12, "description": "invalid parameter value", "param": "user"},
        })
        with self.assertLogs(self.api_module._LOGGER, level="WARNING"):
            with self.assertRaises(self.api_module.TwoNDeviceRejectedError) as ctx:
                await api.async_grant_access(0, "UUID-1")
        self.assertEqual(ctx.exception.kind, "other")
        self.assertIsInstance(ctx.exception, self.api_module.TwoNAPIError)

    async def test_grant_access_timeout_raises_connection_error(self) -> None:
        import asyncio

        api = self._make_api({"success": True})

        async def boom():
            raise asyncio.TimeoutError("slow")

        api.response.json = boom
        with self.assertLogs(self.api_module._LOGGER, level="WARNING"):
            with self.assertRaises(self.api_module.TwoNConnectionError):
                await api.async_grant_access(0, "UUID-1")

    def test_coerce_bool(self) -> None:
        coerce = self.api_module.coerce_bool
        self.assertIs(coerce(True), True)
        self.assertIs(coerce("false"), False)
        self.assertIs(coerce(" TRUE "), True)
        self.assertIs(coerce(1), True)
        self.assertIsNone(coerce("maybe"))
        self.assertIsNone(coerce(None))
        self.assertIsNone(coerce(5))

if __name__ == "__main__":
    unittest.main()
