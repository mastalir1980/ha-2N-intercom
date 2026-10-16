"""DataUpdateCoordinator for 2N Intercom."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import timedelta, datetime
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    CameraTransportInfo,
    TwoNAuthenticationError,
    TwoNConnectionError,
    TwoNIntercomAPI,
    coerce_bool,
)
from .const import (
    ACCESS_LOG_EVENTS,
    CALLED_ID_ALL,
    CAMERA_SOURCES,
    CONF_CAMERA_SOURCE,
    CREDENTIAL_API,
    CREDENTIAL_CARD,
    CREDENTIAL_CODE,
    CREDENTIAL_FINGERPRINT,
    CREDENTIAL_MOBILE_KEY,
    DIRECTORY_CHANGED_EVENT,
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
# A transient 401 must not immediately trigger HA's reauth flow.
NUM_AUTH_ERRORS = 3
# Snapshot cache duration (seconds)
SNAPSHOT_CACHE_DURATION = 1
# Doorbell pulse duration (seconds)
DOORBELL_PULSE_DURATION = 1
# Log listener backoff bounds
LOG_LISTENER_INITIAL_BACKOFF = 5
LOG_LISTENER_MAX_BACKOFF = 60
LOG_LISTENER_PULL_ERROR_DELAY = 1
LOG_LISTENER_IDLE_DELAY = 1
# Minimum seconds between dir/query refreshes triggered by unknown user uuids
DIRECTORY_REFRESH_MIN_INTERVAL = 60
# How many access sessions remember the credential type of their *Entered event
ACCESS_SESSION_MEMORY = 16

# Events the listener always subscribes to. Optional events (MotionDetected,
# access control, DirectoryChanged) are added only when the device supports
# them, so one unsupported event never breaks the whole subscription.
BASE_LOG_EVENTS = (
    "CallStateChanged",
    "CallSessionStateChanged",
    "SwitchStateChanged",
    "InputChanged",
    "OutputChanged",
    "RegistrationStateChanged",
    "ConfigurationChanged",
    "CapabilitiesChanged",
    "DeviceState",
)

# Credential-presentation events and the credential type they represent.
_CREDENTIAL_EVENTS = {
    "CardEntered": CREDENTIAL_CARD,
    "CodeEntered": CREDENTIAL_CODE,
    "MobKeyEntered": CREDENTIAL_MOBILE_KEY,
    "FingerEntered": CREDENTIAL_FINGERPRINT,
    "ApiAccessRequested": CREDENTIAL_API,
}
# AccessLimited ``type`` values (card/code/finger) mapped to credential types.
_ACCESS_LIMITED_TYPES = {
    "card": CREDENTIAL_CARD,
    "code": CREDENTIAL_CODE,
    "finger": CREDENTIAL_FINGERPRINT,
}


@dataclass(frozen=True)
class AccessEvent:
    """Parsed access-control log event.

    Secrets carried by some 2N events (``code``, card ``uid``, mobile key
    ``authid``) are deliberately never stored.
    """

    event_type: str
    timestamp: datetime
    credential_type: str | None = None
    access_point: int | None = None
    direction: str | None = None
    granted: bool | None = None
    reason: str | None = None
    state: str | None = None
    user_uuid: str | None = None
    user_name: str | None = None
    session: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


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
    last_access_event: AccessEvent | None = None
    ring_snapshot: bytes | None = None
    ring_snapshot_time: datetime | None = None


class TwoNIntercomCoordinator(DataUpdateCoordinator[TwoNIntercomData]):  # type: ignore[misc]
    """Coordinator to manage data updates from 2N Intercom."""

    _RING_STATES = {"ringing", "alerting", "ring"}
    _TERMINAL_CALL_STATES = {
        "idle", "terminated", "ended", "finished", "closed",
        "hangup", "hungup", "disconnected",
    }

    def __init__(
        self,
        hass: HomeAssistant,
        api: TwoNIntercomAPI,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        called_id: str | None = None,
        config_entry: ConfigEntry | None = None,
        ring_snapshot_enabled: bool = False,
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
        self._called_peers: dict[str | None, set[str]] = {}
        self._peer_session_id: str | None = None
        self._last_call_state_value: str = "idle"
        self._ring_pulse_until: datetime | None = None
        self._log_subscription_id: int | None = None
        self._log_listener_task: asyncio.Task[None] | None = None
        self._log_listener_stopped = False
        self._camera_transport_info: CameraTransportInfo | None = None
        self._system_caps: dict[str, str] = {}
        self._motion_detected = False
        self._last_motion_time: datetime | None = None
        # Access control (log events + directory name cache)
        self._log_caps: frozenset[str] | None = None
        self._subscribed_log_events: tuple[str, ...] = ()
        self._log_resubscribe_requested = False
        self._last_access_event: AccessEvent | None = None
        self._access_session_credentials: OrderedDict[
            tuple[int | None, str], str
        ] = OrderedDict()
        self._directory_names: dict[str, str] = {}
        self._directory_refresh_task: asyncio.Task[None] | None = None
        self._directory_last_refresh: float | None = None
        # Last-ring snapshot
        self._ring_snapshot_enabled = ring_snapshot_enabled
        self._ring_snapshot: bytes | None = None
        self._ring_snapshot_time: datetime | None = None

    @staticmethod
    def _normalize_peer(peer: str | None) -> str | None:
        """Return the canonical SIP user, excluding host, parameters and password."""
        if not peer:
            return None
        normalized = peer.strip().lower()
        if normalized == CALLED_ID_ALL:
            return None
        normalized = normalized.removeprefix("sip:").removeprefix("sips:")
        normalized = normalized.split("@", 1)[0].split(";", 1)[0].split(":", 1)[0]
        return normalized.strip() or None

    def _session_called_peers(self, session_id: str | None) -> set[str]:
        """Resolve sessionless events to the most recently observed session."""
        if session_id is None:
            session_id = self._peer_session_id
        elif self._peer_session_id is None and None in self._called_peers:
            self._called_peers.setdefault(session_id, set()).update(
                self._called_peers.pop(None)
            )
        self._peer_session_id = session_id
        return self._called_peers.setdefault(session_id, set())

    def _update_called_peers_from_status(self, call_status: dict[str, Any]) -> None:
        """Merge all current session peers without replacing event evidence."""
        previous_session_id = self._peer_session_id
        current_sessions: set[str | None] = set()
        for session in call_status.get("sessions") or []:
            state = str(
                session.get("state") or call_status.get("state") or ""
            ).strip().lower()
            if state in self._TERMINAL_CALL_STATES:
                continue
            session_id = self._extract_first_nonempty_string(
                session, "session", "sessionNumber"
            )
            peers = self._session_called_peers(session_id)
            current_sessions.add(self._peer_session_id)
            for call in session.get("calls") or []:
                raw_peer = self._extract_first_nonempty_string(call, "peer", "address")
                peer = self._normalize_peer(raw_peer)
                if peer is not None:
                    peers.add(peer)
        self._called_peers = {
            session: peers for session, peers in self._called_peers.items()
            if session in current_sessions
        }
        if previous_session_id in current_sessions:
            self._peer_session_id = previous_session_id
        elif self._active_session_id in current_sessions:
            self._peer_session_id = self._active_session_id
        elif self._peer_session_id not in current_sessions:
            self._peer_session_id = None

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
            self._last_motion_time = dt_util.utcnow()
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
        if port is None or not isinstance(state, (bool, int)) or state not in (0, 1):
            return False
        port_str = str(port)
        if self._io_status is None:
            self.hass.async_create_task(self.async_request_refresh())
            return False
        ports = self._io_status.get("ports") or []
        for entry in ports:
            if isinstance(entry, dict) and str(entry.get("port")) == port_str:
                entry["state"] = int(state)
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
        if port is None or not isinstance(state, (bool, int)) or state not in (0, 1):
            return False
        port_str = str(port)
        if self._io_status is None:
            self.hass.async_create_task(self.async_request_refresh())
            return False
        ports = self._io_status.get("ports") or []
        for entry in ports:
            if isinstance(entry, dict) and str(entry.get("port")) == port_str:
                entry["state"] = int(state)
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
        """Refresh switch, IO and log caps, then notify listeners."""
        await self._refresh_secondary_cache(
            "_switch_caps", "async_get_switch_caps", "switch caps",
        )
        await self._refresh_secondary_cache(
            "_io_caps", "async_get_io_caps", "io caps",
        )
        await self._async_refresh_log_caps()
        if (
            self._log_subscription_id is not None
            and tuple(self._build_log_event_list()) != self._subscribed_log_events
        ):
            self._log_resubscribe_requested = True
        if hasattr(self, "async_update_listeners"):
            self.async_update_listeners()

    # ------------------------------------------------------------------
    # Log caps / subscription list
    # ------------------------------------------------------------------

    async def _async_refresh_log_caps(self) -> None:
        """Fetch /api/log/caps; keep the previous value on any failure."""
        fetcher: Callable[[], Awaitable[list[str] | None]] | None = getattr(
            self.api, "async_get_log_caps", None
        )
        if not callable(fetcher):
            return
        try:
            caps = await fetcher()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Failed to fetch log caps: %s", err)
            return
        if isinstance(caps, (list, tuple, set, frozenset)):
            self._log_caps = frozenset(
                str(event) for event in caps if isinstance(event, str)
            )
        else:
            _LOGGER.debug("Device did not report log caps; access events disabled")

    def _build_log_event_list(self) -> list[str]:
        """Return the events to subscribe to, limited to what the device supports.

        Access-control events and DirectoryChanged are only added when
        /api/log/caps lists them. Without caps they are skipped entirely:
        subscribing to an unsupported event could break the subscription.
        """
        log_events = list(BASE_LOG_EVENTS)
        if self.motion_detection_available:
            log_events.append("MotionDetected")
        if self._log_caps:
            log_events.extend(
                event
                for event in (*ACCESS_LOG_EVENTS, DIRECTORY_CHANGED_EVENT)
                if event in self._log_caps
            )
        return log_events

    # ------------------------------------------------------------------
    # Access control events
    # ------------------------------------------------------------------

    @staticmethod
    def _event_timestamp(event: dict[str, Any]) -> datetime:
        """Return the tz-aware event time from ``utcTime`` (fallback: now)."""
        utc_time = event.get("utcTime")
        if isinstance(utc_time, (int, float)) and not isinstance(utc_time, bool):
            try:
                return dt_util.utc_from_timestamp(utc_time)
            except (OverflowError, OSError, ValueError):
                pass
        return dt_util.utcnow()

    @staticmethod
    def _optional_str(params: dict[str, Any], key: str) -> str | None:
        value = params.get(key)
        if value is None or isinstance(value, (dict, list)):
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def _remember_session_credential(
        self, access_point: int | None, session: str | None, credential: str
    ) -> None:
        if session is None:
            return
        key = (access_point, session)
        self._access_session_credentials[key] = credential
        self._access_session_credentials.move_to_end(key)
        while len(self._access_session_credentials) > ACCESS_SESSION_MEMORY:
            self._access_session_credentials.popitem(last=False)

    def _session_credential(
        self, access_point: int | None, session: str | None
    ) -> str | None:
        if session is None:
            return None
        return self._access_session_credentials.get((access_point, session))

    def _process_access_event(self, event_name: str, event: dict[str, Any]) -> bool:
        """Parse an access-control log event into ``_last_access_event``.

        Field names follow the 2N HTTP API manual (api/log/pull). Returns
        False — without raising — for malformed payloads so one bad event
        never breaks the subscription.
        """
        params = event.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            _LOGGER.debug("Ignoring %s event with malformed params", event_name)
            return False

        access_point = self._optional_int(params.get("ap"))
        session = self._optional_str(params, "session")
        direction = self._optional_str(params, "direction")
        if direction is not None:
            direction = direction.lower()
        uuid = self._optional_str(params, "uuid")
        user_uuid = uuid.lower() if uuid is not None else None
        credential_type: str | None = None
        granted: bool | None = None
        reason: str | None = None
        state: str | None = None

        if event_name in _CREDENTIAL_EVENTS:
            granted = coerce_bool(params.get("valid"))
            if granted is None:
                _LOGGER.debug("Ignoring %s event without a valid flag", event_name)
                return False
            credential_type = _CREDENTIAL_EVENTS[event_name]
            if event_name == "CodeEntered":
                reason = self._optional_str(params, "reason")
            self._remember_session_credential(access_point, session, credential_type)
        elif event_name == "UserAuthenticated":
            granted = True
            credential_type = self._session_credential(access_point, session)
        elif event_name == "UserRejected":
            granted = False
            reason = self._optional_str(params, "reason")
            credential_type = self._session_credential(access_point, session)
        elif event_name == "AccessTaken":
            credential_type = self._session_credential(access_point, session)
        elif event_name in ("AccessBlocked", "AccessLimited"):
            state = (self._optional_str(params, "state") or "").lower() or None
            if state not in ("in", "out"):
                _LOGGER.debug("Ignoring %s event with unknown state", event_name)
                return False
            # "in" = blocking starts (access denied); "out" = blocking ends.
            granted = False if state == "in" else None
            if event_name == "AccessLimited":
                limited_type = (self._optional_str(params, "type") or "").lower()
                credential_type = _ACCESS_LIMITED_TYPES.get(limited_type)
        else:  # pragma: no cover - guarded by ACCESS_LOG_EVENTS dispatch
            return False

        user_name = self._resolve_user_name(
            user_uuid, self._optional_str(params, "name")
        )
        self._last_access_event = AccessEvent(
            event_type=event_name,
            timestamp=self._event_timestamp(event),
            credential_type=credential_type,
            access_point=access_point,
            direction=direction,
            granted=granted,
            reason=reason,
            state=state,
            user_uuid=user_uuid,
            user_name=user_name,
            session=session,
        )
        return True

    def _resolve_user_name(
        self, user_uuid: str | None, event_name: str | None
    ) -> str | None:
        """Return the display name for a user uuid.

        Order: the event's own ``name`` param, then the dir/query cache. An
        unknown uuid schedules a throttled background directory refresh that
        back-fills the name into the latest event.
        """
        if user_uuid is None:
            return event_name
        if event_name:
            self._directory_names[user_uuid] = event_name
            return event_name
        cached = self._directory_names.get(user_uuid)
        if cached is not None:
            return cached
        self._schedule_directory_refresh()
        return None

    def _schedule_directory_refresh(self) -> None:
        task = self._directory_refresh_task
        if task is not None and not task.done():
            return
        now = time.monotonic()
        if (
            self._directory_last_refresh is not None
            and now - self._directory_last_refresh < DIRECTORY_REFRESH_MIN_INTERVAL
        ):
            return
        self._directory_last_refresh = now
        self._directory_refresh_task = self.hass.async_create_task(
            self._async_refresh_directory_names()
        )

    async def _async_refresh_directory_names(self) -> None:
        """Reload the uuid -> name cache from /api/dir/query."""
        fetcher: Callable[[], Awaitable[list[dict[str, str]]]] | None = getattr(
            self.api, "async_get_directory_users", None
        )
        if not callable(fetcher):
            return
        try:
            users = await fetcher()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Failed to refresh directory names: %s", err)
            return

        names: dict[str, str] = {}
        for user in users or []:
            if not isinstance(user, dict):
                continue
            uuid = str(user.get("uuid") or "").strip().lower()
            name = str(user.get("name") or "").strip()
            if uuid and name:
                names[uuid] = name
        self._directory_names = names
        _LOGGER.debug("Directory name cache refreshed (%d users)", len(names))

        event = self._last_access_event
        if (
            event is not None
            and event.user_name is None
            and event.user_uuid is not None
            and event.user_uuid in names
        ):
            self._last_access_event = replace(
                event, user_name=names[event.user_uuid]
            )
            self._publish_event_state()

    def _process_directory_changed_event(self) -> bool:
        """Invalidate the name cache; the next unknown uuid reloads it."""
        self._directory_names = {}
        self._directory_last_refresh = None
        return False

    # ------------------------------------------------------------------
    # Last-ring snapshot
    # ------------------------------------------------------------------

    async def _async_capture_ring_snapshot(self) -> None:
        """Grab a JPEG for the ring that just started.

        Bypasses the 1 s live-view cache so the frame is from the ring. On
        failure the previous ring image is kept.
        """
        transport_info = self._camera_transport_info
        source = transport_info.source if transport_info is not None else None
        try:
            snapshot = await self.api.async_get_snapshot(source=source)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Failed to capture ring snapshot; keeping previous image: %s", err
            )
            return
        if not snapshot:
            _LOGGER.warning(
                "Device returned no ring snapshot; keeping previous image"
            )
            return
        self._ring_snapshot = snapshot
        self._ring_snapshot_time = dt_util.utcnow()
        self._publish_event_state()

    def _publish_event_state(self) -> None:
        """Push event-driven state into ``self.data`` and notify listeners."""
        current: TwoNIntercomData | None = self.data  # type: ignore[has-type]
        if current is not None:
            self.data = replace(
                current,
                last_ring_time=self._last_ring_time,
                active_session_id=self._active_session_id,
                available=True,
                phone_status=self._phone_status or {},
                switch_caps=self._switch_caps or {},
                switch_status=self._switch_status or {},
                io_caps=self._io_caps or {},
                io_status=self._io_status or {},
                last_access_event=self._last_access_event,
                ring_snapshot=self._ring_snapshot,
                ring_snapshot_time=self._ring_snapshot_time,
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
        if event_name in ACCESS_LOG_EVENTS:
            return self._process_access_event(event_name, event)
        if event_name == DIRECTORY_CHANGED_EVENT:
            return self._process_directory_changed_event()

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
            _LOGGER.debug(
                "Call event %s state=None direction=None originator=None "
                "session=None peers=[] decision=not a ring (invalid parameters)",
                event_name,
            )
            return False

        raw_state = params.get("state") or params.get("status")
        state = str(raw_state or "").strip().lower()

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

        direction = str(params.get("direction") or "").strip().lower()
        originator = (self._optional_str(params, "originator") or "").lower()
        peer_session_id = session_id if session_id is not None else self._peer_session_id
        if not state:
            _LOGGER.debug(
                "Call event %s state=%r direction=%r originator=%r "
                "session=%r peers=%s decision=not a ring (missing state)",
                event_name, state, direction, originator, peer_session_id,
                sorted(self._called_peers.get(peer_session_id, set())),
            )
            return False

        if (
            state in self._TERMINAL_CALL_STATES
            and not (self._peer_session_id is None and None in self._called_peers)
        ):
            peers = self._called_peers.get(peer_session_id, set())
        else:
            peers = self._session_called_peers(session_id)
        if raw_peer is not None:
            self._last_called_peer = self._normalize_peer(raw_peer)
            if self._last_called_peer is not None:
                peers.add(self._last_called_peer)

        active_states = self._RING_STATES | {"active", "connected"}

        if session_id is not None and state in active_states:
            self._active_session_id = session_id
        elif state in self._TERMINAL_CALL_STATES and (
            session_id is None or self._active_session_id == session_id
        ):
            self._active_session_id = None

        ring_allowed = (
            self._ring_filter_peer is None
            or self._ring_filter_peer in peers
        )
        if event_name == "CallStateChanged":
            is_ringing = state in self._RING_STATES and direction == "outgoing"
        else:
            is_ringing = (
                state in self._RING_STATES
                and bool(originator)
                and originator != "incoming"
            )
        if is_ringing and ring_allowed:
            # CallStateChanged and CallSessionStateChanged both report one
            # ring; capture the snapshot only on the first of them.
            if not self._ring_detected and self._ring_snapshot_enabled:
                self.hass.async_create_task(self._async_capture_ring_snapshot())
            self._ring_detected = True
            self._last_ring_time = dt_util.utcnow()
            self._ring_pulse_until = (
                self._last_ring_time
                + timedelta(seconds=DOORBELL_PULSE_DURATION)
            )
        elif state not in self._RING_STATES:
            self._ring_detected = False
            self._ring_pulse_until = None

        self._last_call_state_value = state

        decision = "not a ring"
        if is_ringing:
            decision = "rang" if ring_allowed else "filtered by peer"
        _LOGGER.debug(
            "Call event %s state=%r direction=%r originator=%r "
            "session=%r peers=%s decision=%s",
            event_name, state, direction, originator, peer_session_id,
            sorted(peers), decision,
        )
        # A single parallel call can end before the session's other calls ring.
        if (
            event_name == "CallSessionStateChanged"
            and state in self._TERMINAL_CALL_STATES
        ):
            self._called_peers.pop(peer_session_id, None)
            if self._peer_session_id == peer_session_id:
                self._peer_session_id = None

        return True

    async def _async_run_log_subscription(self, subscription_id: int) -> None:
        """Drain events for an established subscription until it errors out."""
        while not self._log_listener_stopped:
            if self._log_resubscribe_requested:
                # The supported event set changed; let the outer loop
                # unsubscribe and resubscribe with the new list.
                self._log_resubscribe_requested = False
                _LOGGER.debug(
                    "Log caps changed; resubscribing log subscription %s",
                    subscription_id,
                )
                return
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
                self._publish_event_state()

            # Some 2N firmware returns from log/pull immediately even when
            # timeout=1 is requested. Without a real delay on empty pulls,
            # that behavior turns this listener into a tight busy-loop.
            if events:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(LOG_LISTENER_IDLE_DELAY)

    async def _async_log_listener_loop(self) -> None:
        """Subscribe to call log events with resilient retry/backoff."""
        backoff = LOG_LISTENER_INITIAL_BACKOFF
        while not self._log_listener_stopped:
            subscription_id: int | None = None
            try:
                await self._async_refresh_log_caps()
                log_events = self._build_log_event_list()
                self._log_resubscribe_requested = False
                subscription_id = await self.api.async_subscribe_log(log_events)
                if subscription_id is not None:
                    self._subscribed_log_events = tuple(log_events)
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

    async def async_config_entry_first_refresh(self) -> None:
        """Consume auth retries within setup, before this coordinator is discarded."""
        for attempt in range(NUM_AUTH_ERRORS):
            previous_auth_errors = self._auth_error_count
            try:
                await super().async_config_entry_first_refresh()
            except ConfigEntryAuthFailed:
                raise
            except ConfigEntryNotReady:
                if (
                    self._auth_error_count == previous_auth_errors
                    or attempt == NUM_AUTH_ERRORS - 1
                ):
                    raise
            else:
                return

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
            self._update_called_peers_from_status(call_status)
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
                last_access_event=self._last_access_event,
                ring_snapshot=self._ring_snapshot,
                ring_snapshot_time=self._ring_snapshot_time,
            )
            
        except TwoNAuthenticationError as err:
            await self.api.async_reset_session()
            self._auth_error_count += 1
            if self._auth_error_count < NUM_AUTH_ERRORS:
                _LOGGER.warning(
                    "Authentication error %s/%s (will retry): %s",
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
            return dt_util.utcnow() <= self._ring_pulse_until
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
    def last_access_event(self) -> AccessEvent | None:
        """Return the most recent parsed access-control event."""
        return self._last_access_event

    @property
    def log_caps(self) -> frozenset[str] | None:
        """Return the log events the device reported in /api/log/caps."""
        return self._log_caps

    @property
    def subscribed_log_events(self) -> tuple[str, ...]:
        """Return the events of the currently active log subscription."""
        return self._subscribed_log_events

    @property
    def ring_snapshot(self) -> bytes | None:
        """Return the JPEG captured at the last ring."""
        return self._ring_snapshot

    @property
    def ring_snapshot_time(self) -> datetime | None:
        """Return when the last-ring JPEG was captured (tz-aware)."""
        return self._ring_snapshot_time

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

    async def async_set_io_output(self, port: str, on: bool) -> bool:
        """Set an IO output and refresh its device-confirmed state."""
        success = await self.api.async_io_control(port, on)
        if success:
            await self.async_request_refresh()
        return success

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
            current_time = dt_util.utcnow()
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
