"""DataUpdateCoordinator for 2N Intercom."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta, datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    CameraTransportInfo,
    TwoNAuthenticationError,
    TwoNConnectionError,
    TwoNIntercomAPI,
)
from .const import (
    CALLED_ID_ALL,
    CAMERA_SOURCES,
    CONF_CAMERA_SOURCE,
    CONF_LIVE_VIEW_MODE,
    CONF_MJPEG_FPS,
    CONF_MJPEG_HEIGHT,
    CONF_MJPEG_WIDTH,
    DEFAULT_LIVE_VIEW_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

# ConfigEntryAuthFailed lives in homeassistant.exceptions but the test stubs
# don't ship it. Import lazily so module load works in any HA shape; raising
# it in real HA still triggers the reauth flow.
try:
    from homeassistant.exceptions import (
        ConfigEntryAuthFailed,
    )
except ImportError:  # pragma: no cover - test stub fallback
    class ConfigEntryAuthFailed(ConfigEntryNotReady):  # type: ignore[no-redef,misc]
        """Fallback for HA stubs that lack ConfigEntryAuthFailed."""

_LOGGER = logging.getLogger(__name__)


@dataclass
class TwoNIntercomRuntimeData:
    """Per-config-entry runtime state held on ``ConfigEntry.runtime_data``.

    Replaces the legacy ``hass.data[DOMAIN][entry.entry_id]`` dict so that
    every consumer (platforms, services, diagnostics) gets a typed handle
    instead of bracket-indexing an untyped dict — see the HA quality-scale
    ``runtime-data`` rule.
    """

    coordinator: TwoNIntercomCoordinator
    api: TwoNIntercomAPI
    loaded_platforms: list[str] = field(default_factory=list)


if TYPE_CHECKING:
    type TwoNIntercomConfigEntry = ConfigEntry[TwoNIntercomRuntimeData]

# Maximum number of retries before giving up
MAX_RETRIES = 5
# Maximum delay between retries (seconds)
MAX_BACKOFF_DELAY = 60
# Consecutive auth failures tolerated before triggering HA's reauth flow.
# A single 401 can come from a stale digest nonce (aiohttp DigestAuthMiddleware
# caches nonce/nc across the long-lived session and the 2N firmware rotates
# nonces over time), a brief device recovery, or a garbled response. Only a
# sustained run indicates the stored credentials actually stopped working —
# matches the platinum reolink integration's NUM_CRED_ERRORS pattern.
NUM_AUTH_ERRORS = 3
# Snapshot cache duration (seconds)
SNAPSHOT_CACHE_DURATION = 1
# Doorbell pulse duration (seconds)
DOORBELL_PULSE_DURATION = 1
# Log listener backoff bounds
LOG_LISTENER_INITIAL_BACKOFF = 5
LOG_LISTENER_MAX_BACKOFF = 60
LOG_LISTENER_PULL_ERROR_DELAY = 1


@dataclass
class TwoNIntercomData:
    """Data structure for 2N Intercom coordinator."""

    call_status: dict[str, Any]
    last_ring_time: datetime | None
    caller_info: dict[str, Any] | None
    active_session_id: str | None
    available: bool
    phone_status: dict[str, Any]
    switch_caps: dict[str, Any]
    switch_status: dict[str, Any]
    io_caps: dict[str, Any]
    io_status: dict[str, Any]


class TwoNIntercomCoordinator(DataUpdateCoordinator[TwoNIntercomData]):  # type: ignore[misc]
    """Coordinator to manage data updates from 2N Intercom."""

    _RING_STATES = {"ringing", "alerting", "incoming", "ring"}

    def __init__(
        self,
        hass: HomeAssistant,
        api: TwoNIntercomAPI,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        called_id: str | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        # HA 2024.10+ accepts config_entry kwarg; pass when available so log
        # lines and unhandled exceptions are tagged with the entry id.
        coordinator_kwargs: dict[str, Any] = {
            "name": DOMAIN,
            "update_interval": timedelta(seconds=scan_interval),
        }
        if config_entry is not None:
            coordinator_kwargs["config_entry"] = config_entry
        try:
            super().__init__(hass, _LOGGER, **coordinator_kwargs)
        except TypeError:
            # Fallback for older HA stubs (e.g. unit tests) without config_entry kwarg.
            coordinator_kwargs.pop("config_entry", None)
            super().__init__(hass, _LOGGER, **coordinator_kwargs)
        self.api = api
        self.config_entry = config_entry
        self._last_call_state: dict[str, Any] = {}
        self._ring_detected = False
        self._last_ring_time: datetime | None = None
        self._active_session_id: str | None = None
        # Note: _retry_count is safe from race conditions because Home Assistant's
        # DataUpdateCoordinator serializes update calls - only one _async_update_data
        # runs at a time
        self._retry_count = 0
        self._auth_error_count = 0
        self._snapshot_cache: bytes | None = None
        self._snapshot_cache_time: datetime | None = None
        self._snapshot_cache_size: tuple[int | None, int | None] | None = None
        self._system_info: dict[str, Any] | None = None
        self._phone_status: dict[str, Any] | None = None
        self._switch_caps: dict[str, Any] | None = None
        self._switch_status: dict[str, Any] | None = None
        self._io_caps: dict[str, Any] | None = None
        self._io_status: dict[str, Any] | None = None
        self._ring_filter_peer = self._normalize_peer(called_id)
        self._last_called_peer: str | None = None
        self._last_call_state_value: str = "idle"
        self._ring_pulse_until: datetime | None = None
        self._log_subscription_id: int | None = None
        self._log_listener_task: asyncio.Task[None] | None = None
        self._log_listener_stopped = False
        self._camera_transport_info: CameraTransportInfo | None = None
        self._system_caps: dict[str, str] = {}
        self._motion_detected = False
        self._last_motion_time: datetime | None = None

    @staticmethod
    def _normalize_peer(peer: str | None) -> str | None:
        if not peer or peer == CALLED_ID_ALL:
            return None
        normalized = peer.replace("sip:", "")
        if "@" in normalized:
            normalized = normalized.split("@", 1)[0]
        return normalized.strip() or None

    @staticmethod
    def _extract_called_peer(call_status: dict[str, Any]) -> str | None:
        sessions = call_status.get("sessions") or []
        if not sessions:
            return None
        calls = sessions[0].get("calls") or []
        if not calls:
            return None
        peer: str | None = calls[0].get("peer")
        return peer

    @staticmethod
    def _extract_call_state(call_status: dict[str, Any]) -> str | None:
        state: str | None = call_status.get("state")
        if state:
            return state

        sessions = call_status.get("sessions") or []
        for session in sessions:
            session_state: str | None = session.get("state")
            if session_state:
                return session_state

            calls = session.get("calls") or []
            for call in calls:
                call_state: str | None = call.get("state") or call.get("status") or call.get("callState")
                if call_state:
                    return call_state

        return None

    @staticmethod
    def _extract_active_session_id(call_status: dict[str, Any]) -> str | None:
        """Return the active call session id, if available."""
        if not isinstance(call_status, dict):
            return None

        active_states = {"ringing", "alerting", "incoming", "active", "connected"}
        sessions = call_status.get("sessions") or []

        for session in sessions:
            if not isinstance(session, dict):
                continue

            candidate = session.get("session")
            if candidate is None:
                continue

            normalized_candidate = str(candidate).strip()
            if not normalized_candidate:
                continue

            state = str(session.get("state") or "").strip().lower()
            if state in active_states:
                return normalized_candidate

        state = str(call_status.get("state") or "").strip().lower()
        if state in active_states:
            session_id = call_status.get("session")
            if session_id is not None:
                normalized_session = str(session_id).strip()
                if normalized_session:
                    return normalized_session

        return None

    @staticmethod
    def _extract_first_nonempty_string(params: dict[str, Any], *keys: str) -> str | None:
        """Return the first non-empty string value for any of the provided keys."""
        for key in keys:
            raw_value = params.get(key)
            if raw_value is None:
                continue

            normalized_value = str(raw_value).strip()
            if normalized_value:
                return normalized_value

        return None

    def _process_motion_event(self, event: dict[str, Any]) -> bool:
        """Handle a MotionDetected log event."""
        params = event.get("params") or {}
        if not isinstance(params, dict):
            return False
        state = str(params.get("state") or "").strip().lower()
        if state == "in":
            self._motion_detected = True
            self._last_motion_time = datetime.now()
            return True
        if state == "out":
            self._motion_detected = False
            return True
        return False

    def _process_switch_state_event(self, params: dict[str, Any]) -> bool:
        """Handle a SwitchStateChanged log event.

        Patches the cached ``_switch_status`` in-place so entities reflect
        the relay state change without waiting for the next poll cycle.
        """
        if not isinstance(params, dict):
            return False
        switch_num = params.get("switch")
        state = params.get("state")
        if not isinstance(switch_num, int) or not isinstance(state, bool):
            return False
        if self._switch_status is None:
            self.hass.async_create_task(self.async_request_refresh())
            return False
        switches = self._switch_status.get("switches") or []
        for entry in switches:
            if isinstance(entry, dict) and entry.get("switch") == switch_num:
                entry["active"] = state
                return True
        return False

    def _process_input_changed_event(self, params: dict[str, Any]) -> bool:
        """Handle an InputChanged log event.

        Patches the cached ``_io_status`` in-place for the matching input port.
        """
        if not isinstance(params, dict):
            return False
        port = params.get("port")
        state = params.get("state")
        if port is None or not isinstance(state, bool):
            return False
        port_str = str(port)
        if self._io_status is None:
            self.hass.async_create_task(self.async_request_refresh())
            return False
        ports = self._io_status.get("ports") or []
        for entry in ports:
            if isinstance(entry, dict) and str(entry.get("port")) == port_str:
                entry["state"] = state
                return True
        return False

    def _process_output_changed_event(self, params: dict[str, Any]) -> bool:
        """Handle an OutputChanged log event.

        Patches the cached ``_io_status`` in-place for the matching output port.
        """
        if not isinstance(params, dict):
            return False
        port = params.get("port")
        state = params.get("state")
        if port is None or not isinstance(state, bool):
            return False
        port_str = str(port)
        if self._io_status is None:
            self.hass.async_create_task(self.async_request_refresh())
            return False
        ports = self._io_status.get("ports") or []
        for entry in ports:
            if isinstance(entry, dict) and str(entry.get("port")) == port_str:
                entry["state"] = state
                return True
        return False

    def _process_registration_event(self, params: dict[str, Any]) -> bool:
        """Handle a RegistrationStateChanged log event.

        Patches the cached ``_phone_status`` in-place for the matching SIP
        account so the phone sensor reflects registration changes immediately.
        """
        if not isinstance(params, dict):
            return False
        sip_account = params.get("sipAccount")
        state = params.get("state")
        if sip_account is None or not isinstance(state, str):
            return False
        if self._phone_status is None:
            self.hass.async_create_task(self.async_request_refresh())
            return False
        accounts = self._phone_status.get("accounts") or []
        for entry in accounts:
            if isinstance(entry, dict) and entry.get("sipAccount") == sip_account:
                entry["state"] = state
                return True
        return False

    def _process_config_changed_event(self) -> bool:
        """Handle a ConfigurationChanged or CapabilitiesChanged log event.

        Schedules an async caps refresh so dynamic entity add/remove picks up
        newly enabled or disabled relays and IO ports.
        """
        self.hass.async_create_task(self._async_refresh_caps_from_event())
        return False  # async task handles notification

    async def _async_refresh_caps_from_event(self) -> None:
        """Refresh switch and IO caps, then notify listeners."""
        await self._refresh_secondary_cache(
            "_switch_caps", "async_get_switch_caps", "switch caps",
        )
        await self._refresh_secondary_cache(
            "_io_caps", "async_get_io_caps", "io caps",
        )
        if hasattr(self, "async_update_listeners"):
            self.async_update_listeners()

    def _process_device_state_event(self, params: dict[str, Any]) -> bool:
        """Handle a DeviceState log event.

        A ``state == "startup"`` means the device just rebooted. Schedule a
        full refresh to re-establish baseline state. The server-side
        subscription is killed by the reboot, so the pull loop will error
        out and the outer loop will resubscribe automatically.
        """
        if not isinstance(params, dict):
            return False
        state = str(params.get("state") or "").strip().lower()
        if state == "startup":
            _LOGGER.info("Device startup detected; scheduling baseline refresh")
            self.hass.async_create_task(self.async_request_refresh())
        return False

    def _process_log_event(self, event: dict[str, Any]) -> bool:
        """Apply a supported log event to coordinator state."""
        if not isinstance(event, dict):
            return False

        event_name = str(event.get("event") or "").strip()

        if event_name == "MotionDetected":
            return self._process_motion_event(event)

        if event_name == "SwitchStateChanged":
            return self._process_switch_state_event(event.get("params") or {})
        if event_name == "InputChanged":
            return self._process_input_changed_event(event.get("params") or {})
        if event_name == "OutputChanged":
            return self._process_output_changed_event(event.get("params") or {})
        if event_name == "RegistrationStateChanged":
            return self._process_registration_event(event.get("params") or {})
        if event_name in ("ConfigurationChanged", "CapabilitiesChanged"):
            return self._process_config_changed_event()
        if event_name == "DeviceState":
            return self._process_device_state_event(event.get("params") or {})

        if event_name not in {"CallStateChanged", "CallSessionStateChanged"}:
            return False

        params = event.get("params") or {}
        if not isinstance(params, dict):
            return False

        raw_state = params.get("state") or params.get("status")
        if raw_state is None:
            return False

        state = str(raw_state).strip().lower()
        if not state:
            return False

        if event_name == "CallSessionStateChanged":
            session_id = self._extract_first_nonempty_string(
                params, "sessionNumber", "session"
            )
            raw_peer = self._extract_first_nonempty_string(
                params, "address", "peer"
            )
        else:
            session_id = self._extract_first_nonempty_string(
                params, "session", "sessionNumber"
            )
            raw_peer = self._extract_first_nonempty_string(
                params, "peer", "address"
            )

        if raw_peer is not None:
            self._last_called_peer = self._normalize_peer(raw_peer)

        direction = str(params.get("direction") or "").strip().lower()
        active_states = self._RING_STATES | {"active", "connected"}
        terminal_states = {
            "idle",
            "terminated",
            "ended",
            "finished",
            "closed",
            "hangup",
            "hungup",
            "disconnected",
        }

        if session_id is not None and state in active_states:
            self._active_session_id = session_id
        elif state in terminal_states and (
            session_id is None or self._active_session_id == session_id
        ):
            self._active_session_id = None

        ring_allowed = (
            self._ring_filter_peer is None
            or self._last_called_peer == self._ring_filter_peer
        )
        is_ringing = state in self._RING_STATES and direction != "outgoing"
        if is_ringing and ring_allowed:
            self._ring_detected = True
            self._last_ring_time = datetime.now()
            self._ring_pulse_until = (
                self._last_ring_time
                + timedelta(seconds=DOORBELL_PULSE_DURATION)
            )
        elif state not in self._RING_STATES:
            self._ring_detected = False
            self._ring_pulse_until = None

        self._last_call_state_value = state

        return True

    async def _async_run_log_subscription(self, subscription_id: int) -> None:
        """Drain events for an established subscription until it errors out."""
        while not self._log_listener_stopped:
            try:
                events = await self.api.async_pull_log(subscription_id, timeout=1)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "Pull failed for log subscription %s: %s", subscription_id, err
                )
                await asyncio.sleep(LOG_LISTENER_PULL_ERROR_DELAY)
                raise

            updated = False
            for event in events:
                updated = self._process_log_event(event) or updated

            if updated:
                current: TwoNIntercomData | None = self.data  # type: ignore[has-type]
                if current is not None:
                    self.data = TwoNIntercomData(
                        call_status=current.call_status,
                        last_ring_time=self._last_ring_time,
                        caller_info=current.caller_info,
                        active_session_id=self._active_session_id,
                        available=True,
                        phone_status=self._phone_status or {},
                        switch_caps=self._switch_caps or {},
                        switch_status=self._switch_status or {},
                        io_caps=self._io_caps or {},
                        io_status=self._io_status or {},
                    )
                if hasattr(self, "async_update_listeners"):
                    self.async_update_listeners()

            # Yield to the loop; the device blocks server-side via timeout=1
            # so this does not become a busy-loop on the success path.
            await asyncio.sleep(0)

    async def _async_log_listener_loop(self) -> None:
        """Subscribe to call log events with resilient retry/backoff."""
        backoff = LOG_LISTENER_INITIAL_BACKOFF
        while not self._log_listener_stopped:
            subscription_id: int | None = None
            try:
                log_events = [
                    "CallStateChanged",
                    "CallSessionStateChanged",
                    "SwitchStateChanged",
                    "InputChanged",
                    "OutputChanged",
                    "RegistrationStateChanged",
                    "ConfigurationChanged",
                    "CapabilitiesChanged",
                    "DeviceState",
                ]
                if self.motion_detection_available:
                    log_events.append("MotionDetected")
                subscription_id = await self.api.async_subscribe_log(log_events)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("Log subscription failed: %s", err)

            if subscription_id is None:
                _LOGGER.debug(
                    "Log subscribe returned no id; retrying in %ss", backoff
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    raise
                backoff = min(backoff * 2, LOG_LISTENER_MAX_BACKOFF)
                continue

            _LOGGER.debug(
                "Log subscription %s established; entering pull loop",
                subscription_id,
            )
            self._log_subscription_id = subscription_id
            backoff = LOG_LISTENER_INITIAL_BACKOFF
            # Re-establish baseline state after (re)connection
            _LOGGER.debug("Subscription established; forcing baseline refresh")
            self.hass.async_create_task(self.async_request_refresh())

            try:
                await self._async_run_log_subscription(subscription_id)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "Log subscription %s dropped: %s; will resubscribe",
                    subscription_id,
                    err,
                )
            finally:
                if self._log_subscription_id == subscription_id:
                    self._log_subscription_id = None
                # Best-effort unsubscribe; ignore failures because the channel
                # may already be gone server-side.
                try:
                    await self.api.async_unsubscribe_log(subscription_id)
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug(
                        "Cleanup unsubscribe for %s failed: %s",
                        subscription_id,
                        err,
                    )

    async def async_start_log_listener(self) -> None:
        """Start the background log-listener task if it is not already running.

        The task is registered against the config entry's background-task pool
        so HA tracks its ownership and cancels it on entry unload. The
        EVENT_HOMEASSISTANT_STOP listener wired up in __init__.py also calls
        async_stop_log_listener() so we get a graceful unsubscribe BEFORE the
        final-writes shutdown stage; otherwise the long-poll task strands and
        HA logs a "still running after final writes shutdown" warning.
        """
        if self._log_listener_task is not None and not self._log_listener_task.done():
            return

        self._log_listener_stopped = False
        coro = self._async_log_listener_loop()
        entry = getattr(self, "config_entry", None)
        if entry is not None:
            self._log_listener_task = entry.async_create_background_task(
                self.hass,
                coro,
                name=f"{DOMAIN} log listener {entry.entry_id}",
                eager_start=True,
            )
        else:
            self._log_listener_task = self.hass.async_create_task(coro)

    async def async_stop_log_listener(self) -> None:
        """Stop the background log-listener task and unsubscribe active channel."""
        self._log_listener_stopped = True
        subscription_id = self._log_subscription_id
        task = self._log_listener_task
        self._log_listener_task = None

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if subscription_id is not None:
            try:
                await self.api.async_unsubscribe_log(subscription_id)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("Failed to unsubscribe log listener %s: %s", subscription_id, err)
            finally:
                if self._log_subscription_id == subscription_id:
                    self._log_subscription_id = None

    async def _refresh_secondary_cache(
        self,
        cache_attr: str,
        method_name: str,
        label: str,
        *,
        log_level: str = "debug",
    ) -> dict[str, Any]:
        """Refresh a cached secondary endpoint, returning the cached value on failure."""
        fetcher: Callable[[], Awaitable[dict[str, Any]]] | None = getattr(
            self.api, method_name, None
        )
        if fetcher is None or not callable(fetcher):
            _LOGGER.debug(
                "API does not expose %s; using cached %s",
                method_name,
                label,
            )
            cached_value = getattr(self, cache_attr)
            return cached_value or {}

        try:
            value = await fetcher()
        except Exception as err:  # pylint: disable=broad-except
            log_message = f"Failed to fetch {label}: %s"
            if log_level == "warning":
                _LOGGER.warning(log_message, err)
            else:
                _LOGGER.debug(log_message, err)
            cached_value = getattr(self, cache_attr)
            return cached_value or {}

        setattr(self, cache_attr, value)
        result: dict[str, Any] = value
        return result

    async def async_initialize_static_caches(self) -> None:
        """Fetch device metadata that does not change at runtime.

        Called once during ``async_setup_entry``. ``switch/caps`` and
        ``io/caps`` are static device descriptors; refetching them every five
        seconds wastes ~17k device requests/day. We resolve them here so the
        per-tick update path can stay focused on real status data.
        """
        if self._system_info is None:
            try:
                self._system_info = await self.api.async_get_system_info()
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("Failed to fetch system info: %s", err)
                self._system_info = {}

        if not self._system_caps:
            try:
                self._system_caps = await self.api.async_get_system_caps()
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("Failed to fetch system caps: %s", err)
                self._system_caps = {}

        if self._switch_caps is None:
            await self._refresh_secondary_cache(
                "_switch_caps",
                "async_get_switch_caps",
                "switch caps",
                log_level="warning",
            )

        if self._io_caps is None:
            await self._refresh_secondary_cache(
                "_io_caps",
                "async_get_io_caps",
                "io caps",
                log_level="warning",
            )

        if self._camera_transport_info is None:
            cam_fetcher: Callable[..., Awaitable[CameraTransportInfo]] | None = getattr(
                self.api, "async_get_camera_transport_info", None
            )
            if callable(cam_fetcher):
                try:
                    self._camera_transport_info = await cam_fetcher(
                        **self._camera_transport_overrides()
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug("Failed to resolve camera transport info: %s", err)
                    self._camera_transport_info = getattr(
                        self.api, "camera_transport_info", None
                    )
            else:
                _LOGGER.debug(
                    "API does not expose async_get_camera_transport_info; "
                    "skipping static transport cache"
                )

    def _camera_transport_overrides(self) -> dict[str, Any]:
        """Return kwargs for ``async_get_camera_transport_info`` from options.

        Reads the user-configurable camera fields from the config entry's
        ``options`` (set via the integration's options flow) and falls back
        to the module defaults when a field hasn't been configured. Unknown
        keys are dropped so older API versions remain compatible.
        """
        overrides: dict[str, Any] = {
            "requested_mode": DEFAULT_LIVE_VIEW_MODE,
        }

        # Skip the RTSP probe when system/caps says rtspServer is not active.
        # Only pass the flag when we have caps data; None lets the API probe
        # normally (backwards-compatible with devices where caps fetch failed).
        if self._system_caps:
            overrides["rtsp_capable"] = self.rtsp_server_available

        entry = self.config_entry
        if entry is None:
            return overrides

        options = dict(entry.options or {})
        live_view_mode = options.get(CONF_LIVE_VIEW_MODE)
        if isinstance(live_view_mode, str) and live_view_mode:
            overrides["requested_mode"] = live_view_mode

        mjpeg_width = options.get(CONF_MJPEG_WIDTH)
        if isinstance(mjpeg_width, int) and mjpeg_width > 0:
            overrides["mjpeg_width"] = mjpeg_width

        mjpeg_height = options.get(CONF_MJPEG_HEIGHT)
        if isinstance(mjpeg_height, int) and mjpeg_height > 0:
            overrides["mjpeg_height"] = mjpeg_height

        mjpeg_fps = options.get(CONF_MJPEG_FPS)
        if isinstance(mjpeg_fps, int) and mjpeg_fps > 0:
            overrides["mjpeg_fps"] = mjpeg_fps

        camera_source = options.get(CONF_CAMERA_SOURCE)
        if isinstance(camera_source, str) and camera_source.strip() in CAMERA_SOURCES:
            overrides["camera_source"] = camera_source.strip()

        return overrides

    async def _async_update_data(self) -> TwoNIntercomData:
        """Fetch data from API."""
        try:
            if self._system_info is None:
                # Fallback path for tests / first refresh that bypass setup_entry.
                try:
                    self._system_info = await self.api.async_get_system_info()
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.debug("Failed to fetch system info: %s", err)
                    self._system_info = {}

            phone_status = await self._refresh_secondary_cache(
                "_phone_status",
                "async_get_phone_status",
                "phone status",
            )
            # switch_caps: fetched at startup, refreshed on
            # ConfigurationChanged/CapabilitiesChanged events, and
            # unconditionally on every poll cycle as a safety net.
            switch_caps = await self._refresh_secondary_cache(
                "_switch_caps",
                "async_get_switch_caps",
                "switch caps",
            )
            switch_status = await self._refresh_secondary_cache(
                "_switch_status",
                "async_get_switch_status",
                "switch status",
            )
            if self._io_caps is None:
                await self._refresh_secondary_cache(
                    "_io_caps",
                    "async_get_io_caps",
                    "io caps",
                    log_level="warning",
                )
            io_caps = self._io_caps or {}
            io_status = await self._refresh_secondary_cache(
                "_io_status",
                "async_get_io_status",
                "io status",
            )

            # Get current call status
            call_status = await self.api.async_get_call_status()

            # Reset retry / auth-failure counters on successful update
            self._retry_count = 0
            self._auth_error_count = 0

            # Baseline state capture — ring detection is event-driven via
            # CallStateChanged / CallSessionStateChanged subscriptions;
            # the poll only refreshes session and peer baselines.
            current_state = self._extract_call_state(call_status) or "idle"
            self._active_session_id = self._extract_active_session_id(call_status)
            self._last_called_peer = self._normalize_peer(
                self._extract_called_peer(call_status)
            )
            self._last_call_state = call_status
            self._last_call_state_value = current_state

            # Extract caller info
            caller_info = call_status.get("caller", {})
            
            return TwoNIntercomData(
                call_status=call_status,
                last_ring_time=self._last_ring_time,
                caller_info=caller_info if caller_info else None,
                active_session_id=self._active_session_id,
                available=True,
                phone_status=phone_status,
                switch_caps=switch_caps,
                switch_status=switch_status,
                io_caps=io_caps,
                io_status=io_status,
            )
            
        except TwoNAuthenticationError as err:
            # Tolerate a short run of 401s before surfacing reauth. A single
            # 401 is frequently transient (stale digest nonce, brief device
            # recovery, garbled response) and clears on the next tick once
            # aiohttp's DigestAuthMiddleware renegotiates; the user's stored
            # credentials are still correct in that case. Only when we see
            # NUM_AUTH_ERRORS in a row without an intervening success do we
            # raise ConfigEntryAuthFailed, which registers via
            # config_flow.async_step_reauth to prompt for new credentials.
            #
            # Reset the HTTP session proactively so the next poll rebuilds the
            # DigestAuthMiddleware from scratch — this turns "wait for the
            # middleware to notice the stale challenge" into a deterministic
            # fresh handshake on the next attempt.
            try:
                await self.api.async_reset_session()
            except Exception as reset_err:  # pylint: disable=broad-except
                _LOGGER.debug("Session reset after auth error failed: %s", reset_err)
            self._auth_error_count += 1
            if self._auth_error_count < NUM_AUTH_ERRORS:
                _LOGGER.warning(
                    "Authentication error %s/%s (will retry next poll): %s",
                    self._auth_error_count,
                    NUM_AUTH_ERRORS,
                    err,
                )
                raise UpdateFailed(f"Authentication error: {err}") from err
            _LOGGER.error(
                "Authentication failed after %s consecutive attempts: %s",
                self._auth_error_count,
                err,
            )
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
            
        except (TwoNConnectionError, ConnectionError, TimeoutError) as err:
            # Connection errors - use retry counter for tracking
            # Note: Home Assistant's DataUpdateCoordinator handles the actual retry timing
            # via the update_interval. We track retries here for logging and decision making.
            if self._retry_count < MAX_RETRIES:
                self._retry_count += 1
                # Calculate expected delay for informational logging
                expected_delay = min(2 ** self._retry_count, MAX_BACKOFF_DELAY)
                _LOGGER.warning(
                    "Connection error (retry %s/%s, coordinator will retry per update_interval ~%ss): %s",
                    self._retry_count,
                    MAX_RETRIES,
                    expected_delay,
                    err,
                )
                raise UpdateFailed(f"Connection error: {err}") from err
            else:
                # Max retries exceeded - require integration reload
                _LOGGER.error(
                    "Max retries (%s) exceeded for connection to device",
                    MAX_RETRIES,
                )
                raise ConfigEntryNotReady(
                    f"Failed to connect after {MAX_RETRIES} retries"
                ) from err
                
        except Exception as err:
            # Generic API errors - mark entities unavailable but keep trying
            _LOGGER.warning("API error: %s", err)
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    @property
    def ring_active(self) -> bool:
        """Return if doorbell is currently ringing."""
        if self.data:
            if not self._ring_detected:
                return False
            if self._ring_pulse_until is None:
                return False
            return datetime.now() <= self._ring_pulse_until
        return False

    @property
    def last_ring_time(self) -> datetime | None:
        """Return last ring timestamp."""
        return self._last_ring_time

    @property
    def caller_info(self) -> dict[str, Any]:
        """Return caller information."""
        if self.data and self.data.caller_info:
            return self.data.caller_info
        return {}

    @property
    def called_peer(self) -> str | None:
        """Return the last called peer from call status."""
        return self._last_called_peer

    @property
    def call_state(self) -> str | None:
        """Return the last detected call state."""
        return self._last_call_state_value or None

    @property
    def active_session_id(self) -> str | None:
        """Return the last detected active call session id."""
        return self._active_session_id

    @property
    def system_info(self) -> dict[str, Any]:
        """Return cached system info."""
        return self._system_info or {}

    @property
    def phone_status(self) -> dict[str, Any]:
        """Return cached phone status."""
        return self._phone_status or {}

    @property
    def switch_caps(self) -> dict[str, Any]:
        """Return cached switch capabilities."""
        return self._switch_caps or {}

    async def async_refresh_switch_caps(self) -> None:
        """Force an immediate refresh of switch capabilities.

        Call this after learning that the device configuration changed
        (e.g. via a log event) to pick up new relays immediately.
        """
        await self._refresh_secondary_cache(
            "_switch_caps",
            "async_get_switch_caps",
            "switch caps",
        )
        self.async_set_updated_data(self.data)

    @property
    def enabled_switch_numbers(self) -> set[int]:
        """Return the set of relay numbers that are currently enabled."""
        switches = (self._switch_caps or {}).get("switches") or []
        return {
            s["switch"]
            for s in switches
            if isinstance(s, dict) and s.get("enabled") and isinstance(s.get("switch"), int)
        }

    @property
    def switch_status(self) -> dict[str, Any]:
        """Return cached switch status."""
        return self._switch_status or {}

    @property
    def io_caps(self) -> dict[str, Any]:
        """Return cached IO capabilities."""
        return self._io_caps or {}

    @property
    def io_status(self) -> dict[str, Any]:
        """Return cached IO status."""
        return self._io_status or {}

    @property
    def system_caps(self) -> dict[str, str]:
        """Return cached system capabilities."""
        return self._system_caps or {}

    @property
    def rtsp_server_available(self) -> bool:
        """Return True when the device has RTSP server active."""
        cap = self._system_caps.get("rtspServer", "")
        parts = [p.strip() for p in cap.split(",")]
        return "active" in parts

    @property
    def motion_detection_available(self) -> bool:
        """Return True when the device has motion detection active."""
        cap = self._system_caps.get("motionDetection", "")
        parts = [p.strip() for p in cap.split(",")]
        return "active" in parts

    @property
    def motion_detected(self) -> bool:
        """Return True when motion is currently detected."""
        return self._motion_detected

    @property
    def last_motion_time(self) -> datetime | None:
        """Return the timestamp of the last motion detection start."""
        return self._last_motion_time

    @property
    def camera_transport_info(self) -> CameraTransportInfo:
        """Return the camera transport info resolved during setup."""
        if self._camera_transport_info is not None:
            return self._camera_transport_info
        return self.api.camera_transport_info

    def get_device_info(self, entry_id: str, name: str) -> DeviceInfo:
        """Build device info for entities."""
        # Import here to support both real HA and lightweight test stubs.
        from homeassistant.helpers.device_registry import (  # noqa: C0415
            CONNECTION_NETWORK_MAC as _MAC,
            DeviceInfo as _DeviceInfo,
        )

        system_info = self.system_info
        model = system_info.get("variant") or system_info.get("deviceName") or "IP Intercom"
        sw_version = system_info.get("swVersion") or "1.0.0"

        info = _DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=name,
            manufacturer="2N",
            model=model,
            sw_version=sw_version,
        )
        serial = system_info.get("serialNumber")
        if serial:
            info["serial_number"] = str(serial)
        hw_version = system_info.get("hwVersion")
        if hw_version:
            info["hw_version"] = str(hw_version)
        mac = system_info.get("macAddr")
        if mac:
            info["connections"] = {(_MAC, str(mac))}
        return info

    async def async_trigger_relay(
        self, relay: int, duration: int = 2000
    ) -> bool:
        """
        Trigger a relay.
        
        Args:
            relay: Relay number (1-4)
            duration: Pulse duration in milliseconds
            
        Returns:
            True if successful
        """
        try:
            success = await self.api.async_switch_control(
                relay=relay,
                action="trigger",
                duration=duration,
            )
            
            if success:
                _LOGGER.info("Relay %s triggered successfully", relay)
            else:
                _LOGGER.warning("Failed to trigger relay %s", relay)
                
            return success
            
        except Exception as err:
            _LOGGER.error("Error triggering relay %s: %s", relay, err)
            return False

    async def async_get_snapshot(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Get camera snapshot with caching to reduce API load."""
        try:
            # Check cache to avoid excessive API calls
            current_time = datetime.now()
            requested_size = (width, height)

            if (
                self._snapshot_cache is not None
                and self._snapshot_cache_time is not None
                and self._snapshot_cache_size == requested_size
                and (current_time - self._snapshot_cache_time).total_seconds() < SNAPSHOT_CACHE_DURATION
            ):
                _LOGGER.debug("Returning cached snapshot")
                return self._snapshot_cache

            # Pass the configured camera source through so users with an
            # external camera module on the 2N device get snapshots from the
            # right sensor — without it, ``api.async_get_snapshot`` would
            # always fall back to ``DEFAULT_CAMERA_SOURCE = "internal"``.
            transport_info = self._camera_transport_info
            snapshot_source = (
                transport_info.source if transport_info is not None else None
            )
            snapshot = await self.api.async_get_snapshot(
                width=width, height=height, source=snapshot_source
            )
            
            if snapshot:
                self._snapshot_cache = snapshot
                self._snapshot_cache_time = current_time
                self._snapshot_cache_size = requested_size
                _LOGGER.debug("Fetched new snapshot from API")
            
            return snapshot
            
        except Exception as err:
            _LOGGER.error("Error getting snapshot: %s", err)
            return None
