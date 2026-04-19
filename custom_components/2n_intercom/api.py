"""2N Intercom API Client."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
from datetime import datetime
import logging
import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp
import async_timeout

from .const import (
    CAMERA_MJPEG_FPS_MAX,
    CAMERA_MJPEG_FPS_MIN,
    DEFAULT_CAMERA_MJPEG_FPS,
    DEFAULT_CAMERA_MJPEG_HEIGHT,
    DEFAULT_CAMERA_MJPEG_WIDTH,
    DEFAULT_CAMERA_SOURCE,
    DEFAULT_LIVE_VIEW_MODE,
    LIVE_VIEW_MODE_JPEG_ONLY,
    LIVE_VIEW_MODE_MJPEG,
    LIVE_VIEW_MODE_RTSP,
)

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10
RTSP_PATH = "h264_stream"
CAMERA_CAPS_PATH = "/api/camera/caps"
CAMERA_SNAPSHOT_PATH = "/api/camera/snapshot"
PHONE_STATUS_PATH = "/api/phone/status"
SWITCH_CAPS_PATH = "/api/switch/caps"
SWITCH_STATUS_PATH = "/api/switch/status"
IO_CAPS_PATH = "/api/io/caps"
IO_STATUS_PATH = "/api/io/status"
RTSP_PROBE_TIMEOUT = 3

_RESOLUTION_RE = re.compile(r"^\s*(\d+)\s*x\s*(\d+)\s*$")
_CAMERA_SOURCE_KEYS = {"source", "sources", "videosource", "camerasource"}
_CAMERA_CAPS_KEYS = {"caps", "camera", "jpeg", "resolution", "resolutions"}


# 2N error-code constants. The HTTP API manual (section "Error codes")
# documents the master table. The values that matter to this integration:
#
#   8  – invalid authentication method (Basic on a Digest-only endpoint)
#   11 – missing mandatory parameter (``param`` carries the field name)
#   12 – invalid parameter value     (``param`` carries the field name)
#   13 – parameter data too big      (``param`` carries the field name)
#   14 – unspecified processing error — **catch-all**, disambiguate by
#        ``description``. Known overloads observed on firmware 2.50.0.76.2:
#          - "session not found"        (idempotent for hangup)
#          - "Unsupported Content-Type" (request rejected, action failed)
#
# Treat the master table as documentation only — do NOT remap codes here.
# The whole point of the helpers below is that the code itself is rarely
# enough; the description string is the disambiguator.
TWON_ERROR_CODE_UNSPECIFIED = 14


@dataclass(frozen=True)
class TwoNDeviceError:
    """Structured representation of a 2N HTTP API ``error`` payload."""

    code: int | None
    description: str
    param: str | None

    @property
    def description_lower(self) -> str:
        """Return the description normalized for case-insensitive matching."""
        return self.description.strip().lower()

    def is_unspecified_session_not_found(self) -> bool:
        """Return True for ``code 14 + "...not found..."`` payloads.

        This is the only flavour of code 14 that the call-control helpers
        treat as success: the post-condition (no such session) is already
        true, so the hangup is idempotent. Every other code-14 flavour
        — most notably ``"Unsupported Content-Type"`` — is a real failure
        and must surface as a WARNING in the logs.
        """
        return (
            self.code == TWON_ERROR_CODE_UNSPECIFIED
            and "not found" in self.description_lower
        )

    def format(self) -> str:
        """Return a single-line, log-friendly representation."""
        parts = [f"code={self.code}"]
        if self.description:
            parts.append(f"description={self.description!r}")
        if self.param:
            parts.append(f"param={self.param!r}")
        return " ".join(parts)


def parse_device_error(payload: Any) -> TwoNDeviceError | None:
    """Parse a 2N response payload into a :class:`TwoNDeviceError`.

    The 2N firmware reports failures as
    ``{"success": false, "error": {"code": int, "description": str,
    "param"?: str}}``. Returns ``None`` for successful or unrecognized
    payloads so call-sites can use ``is None`` to mean "nothing went
    wrong as far as the device is concerned."
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("success", False):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        # ``success: false`` without an ``error`` block is itself an
        # anomaly worth flagging — preserve that distinction so callers
        # can still log it instead of pretending nothing happened.
        return TwoNDeviceError(code=None, description="", param=None)
    code_raw = error.get("code")
    code = code_raw if isinstance(code_raw, int) else None
    description = str(error.get("description") or "").strip()
    param_raw = error.get("param")
    param = str(param_raw).strip() if param_raw not in (None, "") else None
    return TwoNDeviceError(code=code, description=description, param=param)


def log_device_error(
    level: int,
    action: str,
    path: str,
    params: dict[str, Any] | None,
    error: TwoNDeviceError,
) -> None:
    """Emit a uniformly formatted log line for a device-side failure.

    Centralizing the format means every call site renders the same
    ``code=… description=… param=…`` shape, so grepping the HA log for
    ``"2n_intercom"`` is enough to find every device-rejected request.
    """
    _LOGGER.log(
        level,
        "2N action %s rejected by device at %s params=%s: %s",
        action,
        path,
        params,
        error.format(),
    )


@dataclass(frozen=True)
class CameraResolution:
    """Normalized camera resolution."""

    width: int
    height: int

    def as_tuple(self) -> tuple[int, int]:
        """Return the resolution as a tuple."""
        return (self.width, self.height)

    def as_string(self) -> str:
        """Return the resolution as WIDTHxHEIGHT."""
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class CameraCapabilities:
    """Normalized camera capabilities from camera/caps."""

    jpeg_resolutions: tuple[CameraResolution, ...] = ()
    sources: tuple[str, ...] = ()

    def preferred_source(self) -> str:
        """Return the preferred source for snapshot/MJPEG URLs."""
        if self.sources:
            return self.sources[0]
        return DEFAULT_CAMERA_SOURCE


@dataclass(frozen=True)
class CameraTransportInfo:
    """Normalized camera transport decision and capability state."""

    requested_mode: str = DEFAULT_LIVE_VIEW_MODE
    selected_mode: str = LIVE_VIEW_MODE_JPEG_ONLY
    resolved: bool = False
    live_view_available: bool = False
    rtsp_available: bool = False
    mjpeg_available: bool = False
    mjpeg_public_url_available: bool = False
    jpeg_snapshot_available: bool = True
    capabilities: CameraCapabilities = CameraCapabilities()
    mjpeg_width: int = DEFAULT_CAMERA_MJPEG_WIDTH
    mjpeg_height: int = DEFAULT_CAMERA_MJPEG_HEIGHT
    mjpeg_fps: int = DEFAULT_CAMERA_MJPEG_FPS
    source: str = DEFAULT_CAMERA_SOURCE


def _unique_in_order(values: list[str]) -> tuple[str, ...]:
    """Return unique strings preserving first-seen order."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return tuple(unique)


def _coerce_int(value: Any) -> int | None:
    """Coerce a value to int when possible."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _parse_resolution_string(value: str) -> CameraResolution | None:
    """Parse WIDTHxHEIGHT strings into CameraResolution."""
    match = _RESOLUTION_RE.match(value)
    if match is None:
        return None
    return CameraResolution(width=int(match.group(1)), height=int(match.group(2)))


def _collect_camera_sources(value: Any) -> list[str]:
    """Collect normalized camera sources from a source subtree."""
    sources: list[str] = []
    metadata_keys = {"available", "default", "enabled", "supported"}

    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            sources.append(normalized)
        return sources

    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).strip()
            if isinstance(child, (dict, list, tuple, set)):
                if (
                    isinstance(child, dict)
                    and normalized_key
                    and normalized_key.lower() not in _CAMERA_SOURCE_KEYS
                    and normalized_key.lower() not in metadata_keys
                ):
                    sources.append(normalized_key)
                sources.extend(_collect_camera_sources(child))
                continue
            if isinstance(child, str):
                normalized = child.strip()
                if normalized:
                    sources.append(normalized)
        return sources

    if isinstance(value, (list, tuple, set)):
        for child in value:
            sources.extend(_collect_camera_sources(child))

    return sources


def parse_camera_caps(payload: dict[str, Any] | None) -> CameraCapabilities:
    """Parse camera/caps into a normalized capability object."""
    if not isinstance(payload, dict):
        return CameraCapabilities()

    root = payload.get("result", payload)
    resolutions: list[CameraResolution] = []
    sources: list[str] = []
    resolution_keys_seen: set[tuple[int, int]] = set()

    def visit(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            width = _coerce_int(value.get("width"))
            height = _coerce_int(value.get("height"))
            if width is not None and height is not None:
                resolution = CameraResolution(width=width, height=height)
                if resolution.as_tuple() not in resolution_keys_seen:
                    resolution_keys_seen.add(resolution.as_tuple())
                    resolutions.append(resolution)

            for key, child in value.items():
                normalized_key = str(key).lower()
                if normalized_key in _CAMERA_SOURCE_KEYS:
                    sources.extend(_collect_camera_sources(child))

                if isinstance(child, str):
                    child_res = _parse_resolution_string(child)
                    if child_res is not None and child_res.as_tuple() not in resolution_keys_seen:
                        resolution_keys_seen.add(child_res.as_tuple())
                        resolutions.append(child_res)

                if normalized_key in _CAMERA_CAPS_KEYS or isinstance(child, (dict, list, tuple, set)):
                    visit(child, normalized_key)
            return

        if isinstance(value, (list, tuple, set)):
            for child in value:
                visit(child, parent_key)
            return

        if isinstance(value, str):
            resolution_val: CameraResolution | None = _parse_resolution_string(value)
            if resolution_val is not None and resolution_val.as_tuple() not in resolution_keys_seen:
                resolution_keys_seen.add(resolution_val.as_tuple())
                resolutions.append(resolution_val)
            elif parent_key in _CAMERA_SOURCE_KEYS:
                sources.extend(_collect_camera_sources(value))

    visit(root)

    return CameraCapabilities(
        jpeg_resolutions=tuple(resolutions),
        sources=_unique_in_order(sources),
    )


def validate_mjpeg_fps(fps: int) -> int:
    """Validate and normalize MJPEG FPS."""
    if not CAMERA_MJPEG_FPS_MIN <= fps <= CAMERA_MJPEG_FPS_MAX:
        raise ValueError(
            f"MJPEG fps must be between {CAMERA_MJPEG_FPS_MIN} and {CAMERA_MJPEG_FPS_MAX}"
        )
    return fps


def select_live_view_mode(
    *,
    rtsp_available: bool,
    mjpeg_available: bool,
    requested_mode: str = DEFAULT_LIVE_VIEW_MODE,
) -> str:
    """Select the best live view mode for the device."""
    if requested_mode == LIVE_VIEW_MODE_JPEG_ONLY:
        return LIVE_VIEW_MODE_JPEG_ONLY

    if requested_mode == LIVE_VIEW_MODE_RTSP:
        if rtsp_available:
            return LIVE_VIEW_MODE_RTSP
        if mjpeg_available:
            return LIVE_VIEW_MODE_MJPEG
        return LIVE_VIEW_MODE_JPEG_ONLY

    if requested_mode == LIVE_VIEW_MODE_MJPEG:
        if mjpeg_available:
            return LIVE_VIEW_MODE_MJPEG
        if rtsp_available:
            return LIVE_VIEW_MODE_RTSP
        return LIVE_VIEW_MODE_JPEG_ONLY

    if rtsp_available:
        return LIVE_VIEW_MODE_RTSP
    if mjpeg_available:
        return LIVE_VIEW_MODE_MJPEG
    return LIVE_VIEW_MODE_JPEG_ONLY


class TwoNIntercomAPI:
    """API client for 2N Intercom."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        protocol: str = "https",
        verify_ssl: bool = False,
        session: aiohttp.ClientSession | None = None,
        rtsp_username: str | None = None,
        rtsp_password: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol
        self.verify_ssl = verify_ssl
        self.rtsp_username = rtsp_username
        self.rtsp_password = rtsp_password
        self._session: aiohttp.ClientSession | None = session
        self._owns_session: bool = session is None
        self._base_url = f"{protocol}://{host}:{port}"
        self._camera_capabilities = CameraCapabilities()
        self._camera_transport_info = CameraTransportInfo(
            requested_mode=DEFAULT_LIVE_VIEW_MODE,
            selected_mode=LIVE_VIEW_MODE_RTSP,
            resolved=False,
        )
        self._camera_transport_resolved = False

    async def async_get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session.

        When a session was injected via ``__init__`` (the HA-managed path),
        it is returned as-is.  A fallback self-managed session is created
        only when no session was injected (e.g. during config-flow
        validation where no HA session helper is available).
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self.verify_ssl),
                middlewares=(
                    aiohttp.DigestAuthMiddleware(
                        self.username,
                        self.password,
                        preemptive=False,
                    ),
                ),
            )
            self._owns_session = True
        return self._session

    def _get_basic_auth(self) -> aiohttp.BasicAuth:
        """Return HTTP BasicAuth for all requests."""
        return aiohttp.BasicAuth(self.username, self.password)

    @staticmethod
    def _requires_basic_auth(response: aiohttp.ClientResponse) -> bool:
        """Return whether a 401 challenge requires HTTP Basic auth."""
        challenge = response.headers.get("WWW-Authenticate", "")
        return response.status == 401 and "basic" in challenge.lower()

    @property
    def camera_capabilities(self) -> CameraCapabilities:
        """Return the last known normalized camera capabilities."""
        return self._camera_capabilities

    @property
    def camera_transport_info(self) -> CameraTransportInfo:
        """Return the last known normalized transport info."""
        return self._camera_transport_info

    @property
    def camera_transport_resolved(self) -> bool:
        """Return whether transport detection has resolved to a stable mode."""
        return self._camera_transport_resolved

    def _build_http_url(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        include_auth: bool = False,
    ) -> str:
        """Build an HTTP/HTTPS URL for external consumers.

        ``include_auth`` defaults to False so the returned URL never leaks the
        intercom credentials into HA logs, dashboards, or diagnostics. The
        camera entity passes username/password to ``MjpegCamera`` separately;
        the only callers that should opt back in are RTSP-style helpers
        whose protocol requires the credentials in the URI.
        """
        auth_prefix = ""
        if include_auth:
            auth_prefix = (
                f"{quote(self.username, safe='')}:{quote(self.password, safe='')}@"
            )
        query = f"?{urlencode(params)}" if params else ""
        return f"{self.protocol}://{auth_prefix}{self.host}:{self.port}{path}{query}"

    @staticmethod
    def _select_mjpeg_resolution(
        capabilities: CameraCapabilities,
        *,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        """Return a suitable MJPEG resolution, falling back to device capabilities."""
        requested = (width, height)
        available = [resolution.as_tuple() for resolution in capabilities.jpeg_resolutions]
        if not available:
            return requested
        if requested in available:
            return requested

        sorted_available = sorted(
            available,
            key=lambda item: (item[0] * item[1], item[0], item[1]),
            reverse=True,
        )
        return sorted_available[0]

    def build_snapshot_url(
        self,
        *,
        width: int = DEFAULT_CAMERA_MJPEG_WIDTH,
        height: int = DEFAULT_CAMERA_MJPEG_HEIGHT,
        source: str = DEFAULT_CAMERA_SOURCE,
        include_auth: bool = False,
    ) -> str:
        """Build a direct snapshot URL."""
        return self._build_http_url(
            CAMERA_SNAPSHOT_PATH,
            params={
                "source": source,
                "width": width,
                "height": height,
            },
            include_auth=include_auth,
        )

    def build_mjpeg_url(
        self,
        *,
        width: int = DEFAULT_CAMERA_MJPEG_WIDTH,
        height: int = DEFAULT_CAMERA_MJPEG_HEIGHT,
        fps: int = DEFAULT_CAMERA_MJPEG_FPS,
        source: str = DEFAULT_CAMERA_SOURCE,
        include_auth: bool = False,
    ) -> str:
        """Build a direct MJPEG URL for consumers that need a ffmpeg-usable source URL."""
        validated_fps = validate_mjpeg_fps(fps)
        return self._build_http_url(
            CAMERA_SNAPSHOT_PATH,
            params={
                "source": source,
                "width": width,
                "height": height,
                "fps": validated_fps,
            },
            include_auth=include_auth,
        )

    @asynccontextmanager
    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        """Send a request using Digest auth middleware with Basic fallback."""
        session = await self.async_get_session()
        url = f"{self._base_url}{path}"
        request_kwargs: dict[str, Any] = {}
        if params is not None:
            request_kwargs["params"] = params
        if json_data is not None:
            request_kwargs["json"] = json_data
        if headers is not None:
            request_kwargs["headers"] = headers

        async with session.request(method, url, **request_kwargs) as response:
            if not self._requires_basic_auth(response):
                yield response
                return

        async with session.request(
            method,
            url,
            auth=self._get_basic_auth(),
            **request_kwargs,
        ) as response:
            yield response

    @asynccontextmanager
    async def _async_request_without_auth(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        """Send a request without Digest/Basic auth handling."""
        url = f"{self._base_url}{path}"
        request_kwargs: dict[str, Any] = {
            "connector": aiohttp.TCPConnector(ssl=self.verify_ssl),
        }
        if params is not None:
            request_kwargs["params"] = params
        if json_data is not None:
            request_kwargs["json"] = json_data
        if headers is not None:
            request_kwargs["headers"] = headers

        async with aiohttp.ClientSession(
            connector=request_kwargs.pop("connector"),
        ) as session:
            async with session.request(method, url, **request_kwargs) as response:
                yield response

    async def async_close(self) -> None:
        """Close the API session if we own it.

        HA-managed sessions (injected via ``__init__``) are cleaned up by
        the ``async_create_clientsession`` lifecycle helper, so we must
        not close them ourselves.
        """
        if not self._owns_session:
            return
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def async_reset_session(self) -> None:
        """Drop the current HTTP session so the next request rebuilds it.

        The aiohttp ``DigestAuthMiddleware`` attached to the session caches
        the server's challenge (realm, nonce, opaque) and an increasing nc
        counter for the life of the session. When the device ages out a
        nonce, the cached state is stale and every subsequent request sees
        401 until the middleware renegotiates. Rebuilding the session is a
        deterministic reset of that state — the next call goes through a
        fresh 401→challenge→response handshake with a new nonce.

        Safe for both ownership modes: HA-managed sessions from
        ``async_create_clientsession`` tolerate being closed early (the
        lifecycle helper is idempotent on an already-closed session), and
        the next ``async_get_session`` will fall back to an owned session
        with the same DigestAuthMiddleware configuration.
        """
        session = self._session
        self._session = None
        self._owns_session = True
        if session is not None and not session.closed:
            await session.close()

    async def async_connect(self) -> bool:
        """
        Establish and validate connection to the intercom.
        
        This method creates a new session and validates connectivity.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Close any existing session first
            await self.async_close()
            
            # Create new session
            await self.async_get_session()
            
            # Test connection by getting call status
            await self.async_get_call_status()
            
            _LOGGER.info("Successfully connected to 2N Intercom at %s", self._base_url)
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to connect to 2N Intercom: %s", err)
            await self.async_close()
            return False

    async def async_reconnect(self) -> bool:
        """
        Force reconnection after error.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        _LOGGER.info("Attempting to reconnect to 2N Intercom")
        return await self.async_connect()

    async def async_test_connection(self) -> bool:
        """Test connection to the intercom."""
        try:
            await self.async_get_call_status()
            return True
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    async def async_get_directory(self) -> list[dict[str, Any]]:
        """Get directory entries from /api/dir/query."""
        try:
            payload = {
                "iterator": {"timestamp": 0},
                "fields": ["name", "callPos.peer"],
            }

            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "POST",
                    "/api/dir/query",
                    json_data=payload,
                ) as response:
                    # Check for authentication errors
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )
                    
                    response.raise_for_status()
                    data = await response.json()
                    
            # Parse directory data.
            # Expected format: {"success": true, "result": {...}} — but
            # historical tolerance for {..., "users": [...]} is preserved.
            if isinstance(data, dict):
                if data.get("success") is False:
                    error = parse_device_error(data)
                    if error is not None:
                        log_device_error(
                            logging.WARNING,
                            "directory query",
                            "/api/dir/query",
                            None,
                            error,
                        )
                    return []

                if "result" in data:
                    result = data.get("result")
                    return result or []

                if "users" in data:
                    users: list[dict[str, Any]] = data.get("users", [])
                    return users

            return []

        except TwoNAuthenticationError:
            # Re-raise authentication errors
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting directory: %s", err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting directory: %s", err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting directory: %s", err)
            raise TwoNAPIError(f"API error: {err}") from err

    async def async_get_call_status(self) -> dict[str, Any]:
        """Get current call status from /api/call/status."""
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    "/api/call/status",
                ) as response:
                    # Check for authentication errors
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            # Expected format: {"success": true, "result": {...}}
            if isinstance(data, dict):
                if data.get("success", False):
                    result: dict[str, Any] = data.get("result", {})
                    return result
                error = parse_device_error(data)
                if error is not None:
                    log_device_error(
                        logging.WARNING,
                        "call status",
                        "/api/call/status",
                        None,
                        error,
                    )
            return {}

        except TwoNAuthenticationError:
            # Re-raise authentication errors
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting call status: %s", err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting call status: %s", err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting call status: %s", err)
            raise TwoNAPIError(f"API error: {err}") from err

    async def _async_get_result_dict(self, path: str, label: str) -> dict[str, Any]:
        """Fetch a JSON result object from a GET endpoint.

        Returns ``{}`` on any device-side or transport failure so the
        coordinator can keep its previous cache instead of crashing,
        but always logs a WARNING with the parsed device error so a
        future "no relays" or "no SIP accounts" surprise is traceable
        back to the actual rejection (e.g. ``code 8 invalid
        authentication method``) instead of looking like an empty
        device.
        """
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request("GET", path) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict):
                if data.get("success", False):
                    result = data.get("result", {})
                    if isinstance(result, dict):
                        return result
                    return {}
                error = parse_device_error(data)
                if error is not None:
                    log_device_error(logging.WARNING, label, path, None, error)
            return {}

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting %s: %s", label, err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting %s: %s", label, err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting %s: %s", label, err)
            raise TwoNAPIError(f"API error: {err}") from err

    async def async_get_phone_status(self) -> dict[str, Any]:
        """Get current phone status from /api/phone/status."""
        return await self._async_get_result_dict(PHONE_STATUS_PATH, "phone status")

    async def async_get_switch_caps(self) -> dict[str, Any]:
        """Get switch capabilities from /api/switch/caps."""
        return await self._async_get_result_dict(SWITCH_CAPS_PATH, "switch caps")

    async def async_get_switch_status(self) -> dict[str, Any]:
        """Get switch status from /api/switch/status."""
        return await self._async_get_result_dict(SWITCH_STATUS_PATH, "switch status")

    async def async_get_io_caps(self) -> dict[str, Any]:
        """Get IO capabilities from /api/io/caps."""
        return await self._async_get_result_dict(IO_CAPS_PATH, "io caps")

    async def async_get_io_status(self) -> dict[str, Any]:
        """Get IO status from /api/io/status."""
        return await self._async_get_result_dict(IO_STATUS_PATH, "io status")

    async def _async_call_action(
        self,
        path: str,
        *,
        params: dict[str, Any],
        method: str = "GET",
    ) -> bool:
        """Send a call-control action request and return success state.

        Device error code 14 is **overloaded** by the 2N firmware: it is
        used both for ``"session not found"`` (the session is already gone,
        which is the desired post-condition for a hangup) AND for
        ``"Unsupported Content-Type"`` (the request was rejected outright,
        the call is still ringing). We can only treat the former as
        success — the latter must surface as a failure or we silently
        mask exactly the bug we shipped this fix for.

        Defaults to GET because the 2N IP Verso firmware (2.50.0.76.2)
        rejects aiohttp's default POST with ``code 14, "Unsupported
        Content-Type"`` while a plain GET — the variant the HTTP API
        manual uses in its own example for ``/api/call/hangup`` — works
        in every test cell of the timing/variant matrix.
        """
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    method,
                    path,
                    params=params,
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict) and data.get("success", False):
                return True

            error = parse_device_error(data)
            if error is None:
                # Non-dict body or some other shape we don't recognize.
                _LOGGER.warning(
                    "2N action %s at %s params=%s returned unparseable "
                    "payload: %r",
                    path,
                    path,
                    params,
                    data,
                )
                return False

            if error.is_unspecified_session_not_found():
                _LOGGER.debug(
                    "2N action %s at %s params=%s reports the session "
                    "is already gone (%s); treating the hangup as a "
                    "successful no-op.",
                    path,
                    path,
                    params,
                    error.format(),
                )
                return True

            log_device_error(logging.WARNING, path, path, params, error)
            return False

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.warning("2N action %s timed out: %s", path, err)
            return False
        except aiohttp.ClientError as err:
            _LOGGER.warning("2N action %s transport error: %s", path, err)
            return False
        except Exception as err:
            _LOGGER.error("2N action %s unexpected error: %s", path, err)
            return False

    async def async_answer_call(self, session_id: str) -> bool:
        """Answer an active call session."""
        return await self._async_call_action(
            "/api/call/answer",
            params={"session": session_id},
        )

    async def async_hangup_call(
        self, session_id: str, reason: str | None = None
    ) -> bool:
        """Hang up an active call session.

        Uses ``GET /api/call/hangup?session=…``, matching the example in
        section 5.7.4 of the 2N HTTP API manual (firmware 2.50). A direct
        side-by-side timing/variant matrix against firmware 2.50.0.76.2
        established that:

        * ``GET`` with or without ``reason=…`` terminates the session in
          every state (connecting, ringing, and even after a 5 s wait).
        * ``POST`` with ``Content-Type: application/x-www-form-urlencoded``
          or ``application/json`` also terminates correctly.
        * ``aiohttp.ClientSession.post(...)`` without an explicit body —
          which is what the integration was sending before this fix —
          produces a request the firmware rejects with ``code: 14,
          description: "Unsupported Content-Type"``. The call keeps
          ringing.

        ``reason`` is accepted for caller compatibility but is **not**
        forwarded by default; pass it only if you have verified the
        device honours it for the call state in question.
        """
        params: dict[str, Any] = {"session": session_id}
        if reason:
            params["reason"] = reason
        return await self._async_call_action(
            "/api/call/hangup",
            params=params,
        )

    async def async_subscribe_log(self, events: list[str] | tuple[str, ...]) -> int | None:
        """Subscribe to log events and return the subscription id."""
        event_filter = ",".join(
            event.strip()
            for event in events
            if isinstance(event, str) and event.strip()
        )
        if not event_filter:
            return None

        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    "/api/log/subscribe",
                    params={"filter": event_filter},
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if not isinstance(data, dict):
                _LOGGER.warning(
                    "2N action log subscribe at /api/log/subscribe "
                    "returned non-dict payload: %r",
                    data,
                )
                return None

            if not data.get("success", False):
                error = parse_device_error(data)
                if error is not None:
                    log_device_error(
                        logging.WARNING,
                        "log subscribe",
                        "/api/log/subscribe",
                        {"filter": event_filter},
                        error,
                    )
                return None

            result = data.get("result", {})
            if not isinstance(result, dict):
                return None

            subscription_id = result.get("id")
            if isinstance(subscription_id, int):
                return subscription_id
            if isinstance(subscription_id, str) and subscription_id.strip().isdigit():
                return int(subscription_id.strip())
            return None

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.warning("2N log subscribe timed out: %s", err)
            return None
        except aiohttp.ClientError as err:
            _LOGGER.warning("2N log subscribe transport error: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("2N log subscribe unexpected error: %s", err)
            return None

    async def async_pull_log(
        self,
        subscription_id: int,
        *,
        timeout: int | None = None,
    ) -> list[dict[str, Any]]:
        """Pull pending events for a log subscription."""
        params: dict[str, Any] = {"id": subscription_id}
        if timeout is not None:
            params["timeout"] = timeout

        try:
            async with async_timeout.timeout(API_TIMEOUT + (timeout or 0)):
                async with self._async_request(
                    "GET",
                    "/api/log/pull",
                    params=params,
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if not isinstance(data, dict):
                _LOGGER.debug(
                    "2N log pull at /api/log/pull returned non-dict "
                    "payload: %r",
                    data,
                )
                return []

            if not data.get("success", False):
                error = parse_device_error(data)
                if error is not None:
                    # Pull failures are logged at DEBUG: the listener
                    # loop has its own backoff + resubscribe path, and
                    # this endpoint is hit roughly once per second so
                    # WARNING-level noise here would drown the log on
                    # any transient device hiccup. The listener loop
                    # is the right place to escalate.
                    log_device_error(
                        logging.DEBUG,
                        "log pull",
                        "/api/log/pull",
                        params,
                        error,
                    )
                return []

            result = data.get("result", {})
            if not isinstance(result, dict):
                return []

            events = result.get("events", [])
            if isinstance(events, list):
                return [event for event in events if isinstance(event, dict)]
            return []

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.debug("2N log pull timed out: %s", err)
            return []
        except aiohttp.ClientError as err:
            _LOGGER.debug("2N log pull transport error: %s", err)
            return []
        except Exception as err:
            _LOGGER.error("2N log pull unexpected error: %s", err)
            return []

    async def async_unsubscribe_log(self, subscription_id: int) -> bool:
        """Unsubscribe from a log-event channel."""
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    "/api/log/unsubscribe",
                    params={"id": subscription_id},
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict):
                if data.get("success", False):
                    return True
                error = parse_device_error(data)
                if error is not None:
                    # Unsubscribing is a teardown step and tolerates
                    # "subscription not found" / stale-id rejections
                    # cleanly, so DEBUG is sufficient here.
                    log_device_error(
                        logging.DEBUG,
                        "log unsubscribe",
                        "/api/log/unsubscribe",
                        {"id": subscription_id},
                        error,
                    )
            return False

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.debug("2N log unsubscribe timed out: %s", err)
            return False
        except aiohttp.ClientError as err:
            _LOGGER.debug("2N log unsubscribe transport error: %s", err)
            return False
        except Exception as err:
            _LOGGER.error("2N log unsubscribe unexpected error: %s", err)
            return False

    async def async_get_system_info(self) -> dict[str, Any]:
        """Get system info from /api/system/info."""
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    "/api/system/info",
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict):
                if data.get("success", False):
                    sys_result: dict[str, Any] = data.get("result", {})
                    return sys_result
                error = parse_device_error(data)
                if error is not None:
                    log_device_error(
                        logging.WARNING,
                        "system info",
                        "/api/system/info",
                        None,
                        error,
                    )
            return {}

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting system info: %s", err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting system info: %s", err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting system info: %s", err)
            raise TwoNAPIError(f"API error: {err}") from err

    async def async_get_system_caps(self) -> dict[str, str]:
        """Get system capabilities from /api/system/caps.

        Returns a dict mapping capability names to their status strings,
        e.g. ``{"motionDetection": "active,licensed", "rtspServer": "inactive,licensed"}``.
        """
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    "/api/system/caps",
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict):
                if data.get("success", False):
                    result = data.get("result", {})
                    options = result.get("options", {})
                    if isinstance(options, dict):
                        return {str(k): str(v) for k, v in options.items()}
                error = parse_device_error(data)
                if error is not None:
                    log_device_error(
                        logging.WARNING,
                        "system caps",
                        "/api/system/caps",
                        None,
                        error,
                    )
            return {}

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.debug("Timeout getting system caps: %s", err)
            return {}
        except aiohttp.ClientError as err:
            _LOGGER.debug("Error getting system caps: %s", err)
            return {}
        except Exception as err:
            _LOGGER.debug("Unexpected error getting system caps: %s", err)
            return {}

    async def async_get_camera_caps(
        self,
        *,
        force_refresh: bool = False,
    ) -> CameraCapabilities:
        """Fetch and normalize camera/caps, degrading gracefully on failures."""
        if (
            self._camera_capabilities.jpeg_resolutions
            or self._camera_capabilities.sources
        ) and not force_refresh:
            return self._camera_capabilities

        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request("GET", CAMERA_CAPS_PATH) as response:
                    if response.status >= 400:
                        response.raise_for_status()
                    data = await response.json()

            self._camera_capabilities = parse_camera_caps(data)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Unable to fetch camera capabilities: %s", err)
            if force_refresh:
                self._camera_capabilities = CameraCapabilities()

        return self._camera_capabilities

    async def async_probe_mjpeg(
        self,
        *,
        capabilities: CameraCapabilities | None = None,
        width: int = DEFAULT_CAMERA_MJPEG_WIDTH,
        height: int = DEFAULT_CAMERA_MJPEG_HEIGHT,
        fps: int = DEFAULT_CAMERA_MJPEG_FPS,
        source: str | None = None,
    ) -> bool:
        """Check whether MJPEG appears available without crashing the integration.

        This detects device capability through the integration's normal auth
        path. Actual camera-entity playback decisions can then choose how to
        use that capability without breaking Digest/Basic fallback semantics.
        """
        try:
            validated_fps = validate_mjpeg_fps(fps)
        except ValueError as err:
            _LOGGER.debug("Skipping MJPEG probe because of invalid fps: %s", err)
            return False

        normalized_caps = capabilities or await self.async_get_camera_caps()
        chosen_width, chosen_height = self._select_mjpeg_resolution(
            normalized_caps,
            width=width,
            height=height,
        )
        chosen_source = source or normalized_caps.preferred_source()

        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    CAMERA_SNAPSHOT_PATH,
                    params={
                        "source": chosen_source,
                        "width": chosen_width,
                        "height": chosen_height,
                        "fps": validated_fps,
                    },
                    headers={"Accept": "multipart/x-mixed-replace,image/jpeg"},
                ) as response:
                    if response.status >= 400:
                        response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").lower()

            return any(
                token in content_type
                for token in ("multipart/", "x-mixed-replace", "mjpeg")
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("MJPEG probe failed: %s", err)
            return False

    async def async_probe_mjpeg_public(
        self,
        *,
        capabilities: CameraCapabilities | None = None,
        width: int = DEFAULT_CAMERA_MJPEG_WIDTH,
        height: int = DEFAULT_CAMERA_MJPEG_HEIGHT,
        fps: int = DEFAULT_CAMERA_MJPEG_FPS,
        source: str | None = None,
    ) -> bool:
        """Check whether MJPEG is available without including credentials in the URL."""
        try:
            validated_fps = validate_mjpeg_fps(fps)
        except ValueError as err:
            _LOGGER.debug("Skipping public MJPEG probe because of invalid fps: %s", err)
            return False

        normalized_caps = capabilities or await self.async_get_camera_caps()
        chosen_width, chosen_height = self._select_mjpeg_resolution(
            normalized_caps,
            width=width,
            height=height,
        )
        chosen_source = source or normalized_caps.preferred_source()

        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request_without_auth(
                    "GET",
                    CAMERA_SNAPSHOT_PATH,
                    params={
                        "source": chosen_source,
                        "width": chosen_width,
                        "height": chosen_height,
                        "fps": validated_fps,
                    },
                    headers={"Accept": "multipart/x-mixed-replace,image/jpeg"},
                ) as response:
                    if response.status >= 400:
                        response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").lower()

            return any(
                token in content_type
                for token in ("multipart/", "x-mixed-replace", "mjpeg")
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Public MJPEG probe failed: %s", err)
            return False

    async def async_probe_rtsp(self) -> bool:
        """Check whether RTSP is available and the configured credentials work.

        The 2N RTSP server has its own user database, independent of the
        HTTP API accounts.  If no RTSP credentials are configured the
        probe returns ``False`` so the transport resolver never picks RTSP
        (the user must explicitly set them in the options flow).

        When credentials *are* configured the probe performs a full Digest
        authentication handshake to confirm the RTSP server accepts them.
        """
        if not self.rtsp_username or not self.rtsp_password:
            _LOGGER.debug("RTSP probe skipped: no RTSP credentials configured")
            return False

        reader = None
        writer = None
        try:
            rtsp_port = self._get_rtsp_port()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, rtsp_port),
                timeout=RTSP_PROBE_TIMEOUT,
            )
            uri = f"rtsp://{self.host}:{rtsp_port}/{RTSP_PATH}"

            # Step 1 — unauthenticated OPTIONS to get the Digest challenge.
            request = (
                f"OPTIONS {uri} RTSP/1.0\r\n"
                "CSeq: 1\r\n"
                "User-Agent: HomeAssistant-2NIntercom\r\n\r\n"
            )
            writer.write(request.encode("ascii"))
            await writer.drain()
            response = await asyncio.wait_for(
                reader.read(1024), timeout=RTSP_PROBE_TIMEOUT
            )
            response_text = response.decode("utf-8", errors="ignore")

            if not response_text.startswith("RTSP/1.0"):
                return False
            if any(code in response_text for code in (" 403 ", " 404 ", " 454 ")):
                return False

            # If the server didn't challenge us (200 OK), RTSP is open.
            if " 200 " in response_text:
                return True

            # Expect a 401 with a Digest challenge.
            if " 401 " not in response_text:
                return False

            auth_header = self._build_rtsp_digest_auth(
                response_text, "OPTIONS", uri
            )
            if auth_header is None:
                _LOGGER.debug("RTSP probe: could not parse Digest challenge")
                return False

            # Step 2 — authenticated OPTIONS.
            auth_request = (
                f"OPTIONS {uri} RTSP/1.0\r\n"
                "CSeq: 2\r\n"
                "User-Agent: HomeAssistant-2NIntercom\r\n"
                f"Authorization: {auth_header}\r\n\r\n"
            )
            writer.write(auth_request.encode("ascii"))
            await writer.drain()
            auth_response = await asyncio.wait_for(
                reader.read(1024), timeout=RTSP_PROBE_TIMEOUT
            )
            auth_text = auth_response.decode("utf-8", errors="ignore")
            if " 200 " in auth_text:
                return True
            _LOGGER.debug("RTSP probe: auth failed — %s", auth_text.split("\r\n")[0])
            return False
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("RTSP probe failed: %s", err)
            return False
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # pylint: disable=broad-except
                    pass

    def _build_rtsp_digest_auth(
        self, challenge_response: str, method: str, uri: str
    ) -> str | None:
        """Build a Digest Authorization header value from a 401 challenge."""
        import hashlib  # noqa: PLC0415

        nonce_match = re.search(r'nonce="([^"]+)"', challenge_response)
        realm_match = re.search(r'realm="([^"]+)"', challenge_response)
        if not nonce_match or not realm_match:
            return None

        nonce = nonce_match.group(1)
        realm = realm_match.group(1)
        qop_match = re.search(r'qop="([^"]+)"', challenge_response)
        qop = qop_match.group(1) if qop_match else None

        username = self.rtsp_username or ""
        password = self.rtsp_password or ""

        ha1 = hashlib.md5(
            f"{username}:{realm}:{password}".encode()
        ).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()

        if qop:
            nc = "00000001"
            cnonce = hashlib.md5(nonce.encode()).hexdigest()[:8]
            digest = hashlib.md5(
                f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
            ).hexdigest()
            return (
                f'Digest username="{username}", realm="{realm}", '
                f'nonce="{nonce}", uri="{uri}", response="{digest}", '
                f'qop={qop}, nc={nc}, cnonce="{cnonce}"'
            )

        digest = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        return (
            f'Digest username="{username}", realm="{realm}", '
            f'nonce="{nonce}", uri="{uri}", response="{digest}"'
        )

    async def async_get_camera_transport_info(
        self,
        *,
        requested_mode: str = DEFAULT_LIVE_VIEW_MODE,
        force_refresh: bool = False,
        mjpeg_width: int | None = None,
        mjpeg_height: int | None = None,
        mjpeg_fps: int | None = None,
        camera_source: str | None = None,
        rtsp_capable: bool | None = None,
    ) -> CameraTransportInfo:
        """Return a normalized transport-info object for the camera entity.

        ``mjpeg_width``/``mjpeg_height``/``mjpeg_fps``/``camera_source`` are
        optional overrides sourced from the integration's options flow. When
        omitted the function falls back to the module-level ``DEFAULT_CAMERA_*``
        values (or the device's preferred source) so existing call sites and
        unit tests keep working unchanged.
        """
        requested_width = (
            mjpeg_width if mjpeg_width is not None else DEFAULT_CAMERA_MJPEG_WIDTH
        )
        requested_height = (
            mjpeg_height if mjpeg_height is not None else DEFAULT_CAMERA_MJPEG_HEIGHT
        )
        requested_fps = validate_mjpeg_fps(
            mjpeg_fps if mjpeg_fps is not None else DEFAULT_CAMERA_MJPEG_FPS
        )
        requested_source = (
            camera_source.strip()
            if isinstance(camera_source, str) and camera_source.strip()
            else None
        )

        if (
            self._camera_transport_resolved
            and not force_refresh
            and self._camera_transport_info.requested_mode == requested_mode
            and self._camera_transport_info.mjpeg_width == requested_width
            and self._camera_transport_info.mjpeg_height == requested_height
            and self._camera_transport_info.mjpeg_fps == requested_fps
            and (
                requested_source is None
                or self._camera_transport_info.source == requested_source
            )
        ):
            return self._camera_transport_info

        capabilities = await self.async_get_camera_caps(force_refresh=force_refresh)
        # Honour an explicit source override only when the device actually
        # advertises it; otherwise fall back to whatever the caps endpoint
        # marks as preferred. The device-side resolver still rejects unknown
        # sources, so this guard mainly prevents a silent typo from breaking
        # the snapshot URL builders.
        if requested_source is not None and (
            not capabilities.sources or requested_source in capabilities.sources
        ):
            source = requested_source
        else:
            source = capabilities.preferred_source()
        resolved_width, resolved_height = self._select_mjpeg_resolution(
            capabilities,
            width=requested_width,
            height=requested_height,
        )

        if rtsp_capable is False:
            _LOGGER.debug(
                "RTSP probe skipped: rtspServer capability not active on device"
            )
            rtsp_available = False
        else:
            rtsp_available = await self.async_probe_rtsp()
        mjpeg_authenticated_available = await self.async_probe_mjpeg(
            capabilities=capabilities,
            width=resolved_width,
            height=resolved_height,
            fps=requested_fps,
            source=source,
        )
        mjpeg_public_url_available = await self.async_probe_mjpeg_public(
            capabilities=capabilities,
            width=resolved_width,
            height=resolved_height,
            fps=requested_fps,
            source=source,
        )
        mjpeg_available = (
            mjpeg_authenticated_available or mjpeg_public_url_available
        )
        selected_mode = select_live_view_mode(
            rtsp_available=rtsp_available,
            mjpeg_available=mjpeg_available,
            requested_mode=requested_mode,
        )
        live_view_available = selected_mode in (LIVE_VIEW_MODE_RTSP, LIVE_VIEW_MODE_MJPEG)
        resolved = True

        self._camera_transport_info = CameraTransportInfo(
            requested_mode=requested_mode,
            selected_mode=selected_mode,
            resolved=resolved,
            live_view_available=live_view_available,
            rtsp_available=rtsp_available,
            mjpeg_available=mjpeg_available,
            mjpeg_public_url_available=mjpeg_public_url_available,
            jpeg_snapshot_available=True,
            capabilities=capabilities,
            mjpeg_width=resolved_width,
            mjpeg_height=resolved_height,
            mjpeg_fps=requested_fps,
            source=source,
        )
        self._camera_transport_resolved = resolved
        return self._camera_transport_info

    async def async_switch_control(
        self, relay: int, action: str = "on", duration: int = 0
    ) -> bool:
        """
        Control relay via /api/switch/ctrl.

        Args:
            relay: Relay number (1-4)
            action: Action to perform ("on", "off", "trigger")
            duration: Duration in milliseconds for trigger action

        Returns:
            True if successful, False otherwise

        Note:
            This is a user-facing action (door opener / lock unlock), so
            any device-side rejection is logged at WARNING with the full
            ``code/description/param`` payload — the user pressed a
            button and deserves to know why it didn't fire.
        """
        params: dict[str, Any] = {
            "switch": relay,
            "action": action,
        }
        if duration > 0:
            params["duration"] = duration

        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    "/api/switch/ctrl",
                    params=params,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict) and data.get("success", False):
                return True

            error = parse_device_error(data)
            if error is not None:
                log_device_error(
                    logging.WARNING,
                    f"switch control relay={relay} action={action}",
                    "/api/switch/ctrl",
                    params,
                    error,
                )
            return False

        except asyncio.TimeoutError as err:
            _LOGGER.warning(
                "2N switch control relay=%s timed out: %s", relay, err
            )
            return False
        except aiohttp.ClientError as err:
            _LOGGER.warning(
                "2N switch control relay=%s transport error: %s", relay, err
            )
            return False
        except Exception as err:
            _LOGGER.error(
                "2N switch control relay=%s unexpected error: %s", relay, err
            )
            return False

    async def async_get_snapshot(
        self,
        width: int | None = None,
        height: int | None = None,
        source: str | None = None,
    ) -> bytes | None:
        """Get camera snapshot from /api/camera/snapshot."""
        try:
            resolved_source = (
                source.strip()
                if isinstance(source, str) and source.strip()
                else DEFAULT_CAMERA_SOURCE
            )
            params: dict[str, Any] = {"source": resolved_source}
            if width is None:
                width = 640
            if height is None:
                height = 480
            params["width"] = width
            params["height"] = height

            async with async_timeout.timeout(API_TIMEOUT):
                async with self._async_request(
                    "GET",
                    CAMERA_SNAPSHOT_PATH,
                    params=params,
                    headers={"Accept": "image/jpeg"},
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    if "image" not in content_type:
                        error_body = await response.text()
                        try:
                            payload = json.loads(error_body)
                        except json.JSONDecodeError:
                            payload = None

                        error = parse_device_error(payload)

                        # 2N firmware refuses any width/height that is not in
                        # /api/camera/caps jpegResolution. HA's entity-registry
                        # preview probes the camera at 80x80, which always falls
                        # outside that list. We retry once at the always-supported
                        # 640x480 size and only escalate if that also fails.
                        if (
                            error is not None
                            and error.code == 12
                            and (width, height) != (640, 480)
                        ):
                            _LOGGER.debug(
                                "Snapshot at %dx%d rejected by device "
                                "(%s); retrying at 640x480",
                                width,
                                height,
                                error.format(),
                            )
                            return await self.async_get_snapshot(
                                width=640, height=480, source=resolved_source
                            )

                        if error is not None:
                            log_device_error(
                                logging.WARNING,
                                "camera snapshot",
                                CAMERA_SNAPSHOT_PATH,
                                params,
                                error,
                            )
                        else:
                            _LOGGER.warning(
                                "Snapshot returned non-image content-type: "
                                "%s body=%s request_url=%s params=%s",
                                content_type,
                                error_body,
                                str(response.url),
                                params,
                            )
                        return None
                    image_bytes: bytes = await response.read()
                    return image_bytes

        except asyncio.TimeoutError as err:
            _LOGGER.warning("2N camera snapshot timed out: %s", err)
            return None
        except aiohttp.ClientError as err:
            _LOGGER.warning("2N camera snapshot transport error: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("2N camera snapshot unexpected error: %s", err)
            return None

    def _get_rtsp_port(self) -> int:
        """Return RTSP port, avoiding HTTP/HTTPS ports."""
        if self.port in (80, 443):
            return 554
        return self.port

    def get_rtsp_url(self) -> str:
        """Return RTSP stream URL with masked credentials for logging."""
        rtsp_port = self._get_rtsp_port()
        user = self.rtsp_username or ""
        return f"rtsp://{user}:****@{self.host}:{rtsp_port}/{RTSP_PATH}"

    def get_rtsp_url_with_credentials(self) -> str | None:
        """Return RTSP stream URL with real credentials.

        Uses the dedicated RTSP credentials because the 2N RTSP server
        has its own user database, independent of the HTTP API accounts.
        Returns ``None`` when no RTSP credentials are configured so
        callers can fall back to MJPEG.
        """
        if not self.rtsp_username or not self.rtsp_password:
            return None
        rtsp_port = self._get_rtsp_port()
        return (
            f"rtsp://{quote(self.rtsp_username, safe='')}:"
            f"{quote(self.rtsp_password, safe='')}@"
            f"{self.host}:{rtsp_port}/{RTSP_PATH}"
        )


class TwoNAuthenticationError(Exception):
    """Authentication failed."""


class TwoNConnectionError(Exception):
    """Connection to intercom failed."""


class TwoNAPIError(Exception):
    """Generic API error."""
