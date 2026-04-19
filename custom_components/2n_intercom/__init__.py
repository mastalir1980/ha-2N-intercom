"""The 2N Intercom integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import TwoNIntercomAPI
from .const import (
    CONF_CALLED_ID,
    CONF_ENABLE_CAMERA,
    CONF_ENABLE_DOORBELL,
    CONF_PROTOCOL,
    CONF_RELAY_DEVICE_TYPE,
    CONF_RELAYS,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_ENABLE_CAMERA,
    DEFAULT_ENABLE_DOORBELL,
    DEFAULT_PROTOCOL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DEVICE_TYPE_GATE,
    DOMAIN,
    SCAN_INTERVAL_MAX,
    SCAN_INTERVAL_MIN,
)
from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

_LOGGER = logging.getLogger(__name__)
_VALID_HANGUP_REASONS = {"normal", "rejected", "busy"}

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _get_option(entry: TwoNIntercomConfigEntry | ConfigEntry, key: str, default: object = None) -> object:
    """Return a behavioral option, preferring entry.options over entry.data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _get_platforms(entry: TwoNIntercomConfigEntry | ConfigEntry) -> list[str]:
    """Get list of platforms to set up based on configuration."""
    platforms: list[str] = []

    if _get_option(entry, CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA):
        platforms.append("camera")

    if _get_option(entry, CONF_ENABLE_DOORBELL, DEFAULT_ENABLE_DOORBELL):
        platforms.append("binary_sensor")

    # Switch platform is always loaded — it auto-detects enabled relays
    # from the device's switch/caps endpoint. Cover is only added when
    # the user has explicitly configured a relay as gate-type.
    platforms.append("switch")

    relays_raw = _get_option(entry, CONF_RELAYS, [])
    relays: list[Any] = list(relays_raw) if isinstance(relays_raw, list) else []
    if any(
        r.get(CONF_RELAY_DEVICE_TYPE) == DEVICE_TYPE_GATE
        for r in relays
        if isinstance(r, dict)
    ):
        platforms.append("cover")

    platforms.append("sensor")

    return platforms


def _is_entry_loaded(entry: ConfigEntry) -> bool:
    """Return True when the entry is actually loaded with valid runtime data."""
    # ConfigEntryState.LOADED is the canonical check in real HA.
    # The fallback handles test stubs that don't expose ConfigEntryState.
    state = getattr(entry, "state", None)
    if state is not None:
        loaded_state = getattr(
            type(state), "LOADED", None
        ) or getattr(state, "LOADED", None)
        if loaded_state is not None and state != loaded_state:
            return False
    return isinstance(
        getattr(entry, "runtime_data", None), TwoNIntercomRuntimeData
    )


def _get_loaded_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return 2N Intercom config entries that are actually loaded."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if _is_entry_loaded(entry)
    ]


def _resolve_service_entry(
    hass: HomeAssistant,
    service_data: dict[str, Any],
) -> ConfigEntry:
    """Return the target config entry for a service call.

    Raises ``ServiceValidationError`` for bad user input (wrong
    config_entry_id, ambiguous target) and ``HomeAssistantError`` for
    runtime problems (no loaded entries).
    """
    entries = _get_loaded_entries(hass)
    if not entries:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_loaded_entries",
        )

    config_entry_id = service_data.get("config_entry_id")
    if config_entry_id:
        for entry in entries:
            if str(entry.entry_id) == str(config_entry_id):
                return entry
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"config_entry_id": str(config_entry_id)},
        )

    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="ambiguous_entry",
        )

    return entries[0]


def _resolve_session_id(
    runtime: TwoNIntercomRuntimeData,
    service_data: dict[str, Any],
) -> str:
    """Return the call session id to act on."""
    session_id = service_data.get("session_id")
    if session_id is not None and str(session_id).strip():
        return str(session_id).strip()

    coordinator_session_id = getattr(runtime.coordinator, "active_session_id", None)
    if coordinator_session_id is not None and str(coordinator_session_id).strip():
        return str(coordinator_session_id).strip()

    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="no_active_session",
    )


def _extract_session_ids_from_status(status: Any) -> list[str]:
    """Pull session ids out of /api/call/status `result` payload."""
    if not isinstance(status, dict):
        return []
    sessions = status.get("sessions")
    if not isinstance(sessions, list):
        return []
    out: list[str] = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        raw = session.get("session")
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            out.append(text)
    return out


def _register_call_services(hass: HomeAssistant) -> None:
    """Register call-control services once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, "answer_call"):
        return

    async def _async_answer_call(call: Any) -> None:
        service_data = dict(getattr(call, "data", {}) or {})
        entry = _resolve_service_entry(hass, service_data)
        runtime: TwoNIntercomRuntimeData = entry.runtime_data
        session_id = _resolve_session_id(runtime, service_data)
        if not await runtime.api.async_answer_call(session_id):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="answer_call_failed",
                translation_placeholders={"session_id": session_id},
            )

    async def _async_hangup_call(call: Any) -> None:
        """Hang up active 2N call sessions.

        Idempotent: if no session id is supplied and no session can be
        discovered live on the device, the call is treated as a successful
        no-op (the desired post-condition — no active call — already holds).
        When the caller does not pin a specific session, every active session
        on the device is hung up so a stale cached id can never strand a real
        ringing call.

        ``reason`` is only forwarded to the device when the caller passes an
        explicit valid value. The default leaves it unset, because firmware
        2.50.0.76.2 silently ignores hangups carrying a ``reason`` for
        outgoing-ringing sessions while still answering ``success: true``.
        """
        service_data = dict(getattr(call, "data", {}) or {})
        entry = _resolve_service_entry(hass, service_data)
        runtime: TwoNIntercomRuntimeData = entry.runtime_data
        api = runtime.api
        coordinator = runtime.coordinator

        raw_reason = service_data.get("reason")
        reason: str | None = None
        if raw_reason is not None:
            if not isinstance(raw_reason, str) or not raw_reason.strip():
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_hangup_reason",
                    translation_placeholders={
                        "reason": str(raw_reason),
                        "valid": ", ".join(sorted(_VALID_HANGUP_REASONS)),
                    },
                )
            normalized_reason = raw_reason.strip().lower()
            if normalized_reason not in _VALID_HANGUP_REASONS:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_hangup_reason",
                    translation_placeholders={
                        "reason": raw_reason,
                        "valid": ", ".join(sorted(_VALID_HANGUP_REASONS)),
                    },
                )
            reason = normalized_reason

        explicit_session = service_data.get("session_id")
        if explicit_session is not None and str(explicit_session).strip():
            session_id = str(explicit_session).strip()
            if not await api.async_hangup_call(session_id, reason=reason):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="hangup_call_failed",
                    translation_placeholders={
                        "session_id": session_id,
                        "reason": reason or "",
                    },
                )
            return

        # No explicit session id — ask the device for the live truth instead
        # of trusting whatever the coordinator last cached. This avoids two
        # observed failure modes: (1) the cached active_session_id was already
        # cleared by the polling loop, and (2) it points at a session the
        # device has since terminated, in which case the device returns
        # code 14 "session not found".
        try:
            status = await api.async_get_call_status()
        except Exception as err:  # noqa: BLE001 — surface as service error
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="call_status_query_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        _LOGGER.debug(
            "2n_intercom.hangup_call: live /api/call/status payload = %s",
            status,
        )

        live_sessions = _extract_session_ids_from_status(status)
        cached = getattr(coordinator, "active_session_id", None)
        _LOGGER.debug(
            "2n_intercom.hangup_call: extracted live sessions=%s, coordinator cached=%s",
            live_sessions,
            cached,
        )
        if not live_sessions:
            # Fall back to whatever the coordinator thought was active so a
            # very-recently-ended call still gets a best-effort hangup;
            # otherwise this is a genuine no-op and we succeed silently.
            if cached is not None and str(cached).strip():
                live_sessions = [str(cached).strip()]
            else:
                _LOGGER.debug(
                    "2n_intercom.hangup_call: no active call sessions; nothing to do"
                )
                return

        failures: list[str] = []
        for session_id in live_sessions:
            _LOGGER.debug(
                "2n_intercom.hangup_call: dispatching hangup for session=%s reason=%s",
                session_id,
                reason,
            )
            ok = await api.async_hangup_call(session_id, reason=reason)
            _LOGGER.debug(
                "2n_intercom.hangup_call: hangup session=%s result=%s",
                session_id,
                ok,
            )
            if not ok:
                failures.append(session_id)

        if failures:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="hangup_partial_failure",
                translation_placeholders={
                    "sessions": ", ".join(failures),
                    "reason": reason or "",
                },
            )

    hass.services.async_register(DOMAIN, "answer_call", _async_answer_call)
    hass.services.async_register(DOMAIN, "hangup_call", _async_hangup_call)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up 2N Intercom services (action-setup rule)."""
    _register_call_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: TwoNIntercomConfigEntry
) -> bool:
    """Set up 2N Intercom from a config entry."""
    # Connection identity lives in entry.data (set by initial setup / reauth /
    # reconfigure). Behavioral preferences live in entry.options (set by the
    # options flow). This separation ensures reauth/reconfigure always win for
    # connection fields and the options flow cannot shadow them.
    conn = entry.data
    verify_ssl = conn.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

    import aiohttp as _aiohttp  # local import — only needed here for the middleware

    session = async_create_clientsession(
        hass,
        verify_ssl=verify_ssl,
        middlewares=(
            _aiohttp.DigestAuthMiddleware(
                conn[CONF_USERNAME],
                conn[CONF_PASSWORD],
                preemptive=False,
            ),
        ),
    )

    # RTSP credentials are optional and live in entry.options because the
    # 2N RTSP server has its own user database, independent of the HTTP
    # API accounts configured in entry.data.
    rtsp_username = str(_get_option(entry, CONF_RTSP_USERNAME) or "") or None
    rtsp_password = str(_get_option(entry, CONF_RTSP_PASSWORD) or "") or None

    api = TwoNIntercomAPI(
        host=conn[CONF_HOST],
        port=conn[CONF_PORT],
        username=conn[CONF_USERNAME],
        password=conn[CONF_PASSWORD],
        protocol=conn.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
        verify_ssl=verify_ssl,
        session=session,
        rtsp_username=rtsp_username,
        rtsp_password=rtsp_password,
    )

    # Honour the per-entry polling interval from the options flow when set,
    # falling back to the module default. Out-of-bounds values are clamped so
    # a hand-edited entry can't accidentally hammer the device or stall ring
    # detection — the options-flow selector enforces the same range.
    raw_scan_interval = _get_option(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    try:
        scan_interval = int(str(raw_scan_interval))
    except (TypeError, ValueError):
        scan_interval = DEFAULT_SCAN_INTERVAL
    scan_interval = max(SCAN_INTERVAL_MIN, min(scan_interval, SCAN_INTERVAL_MAX))

    coordinator = TwoNIntercomCoordinator(
        hass,
        api,
        scan_interval=scan_interval,
        called_id=str(_get_option(entry, CONF_CALLED_ID) or "") or None,
        config_entry=entry,
    )

    # Resolve static device descriptors (system info, switch/io caps, camera
    # transport) once at setup so the per-tick refresh stays focused on real
    # status data and doesn't burn ~17k requests/day re-fetching constants.
    await coordinator.async_initialize_static_caches()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = TwoNIntercomRuntimeData(coordinator=coordinator, api=api)

    await coordinator.async_start_log_listener()

    # Stop the long-poll log listener early in HA shutdown so the in-flight
    # /api/log/pull request can wind down before HA's final-writes stage,
    # otherwise the task is reported as "still running after final writes
    # shutdown stage". Wrapping in entry.async_on_unload makes the listener
    # auto-remove on entry reload so it never stacks.
    async def _async_stop_log_listener_on_shutdown(_event: Event | None = None) -> None:
        await coordinator.async_stop_log_listener()

    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, _async_stop_log_listener_on_shutdown
        )
    )

    platforms = _get_platforms(entry)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    # Remember exactly which platforms were forwarded so unload tears down the
    # same set even if the user later changes options that would shift
    # _get_platforms() output (e.g. adding gate-type relays adds cover).
    entry.runtime_data.loaded_platforms = list(platforms)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(
    hass: HomeAssistant, entry: TwoNIntercomConfigEntry
) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: TwoNIntercomConfigEntry
) -> bool:
    """Unload a config entry."""
    # Use the platform list captured at setup so we tear down exactly what was
    # forwarded; recomputing from the merged data here would lie if options
    # changed (e.g. relay_count went from 0 to 1) and try to unload platforms
    # that were never loaded.
    runtime: TwoNIntercomRuntimeData | None = getattr(entry, "runtime_data", None)
    platforms = (
        runtime.loaded_platforms if runtime and runtime.loaded_platforms
        else _get_platforms(entry)
    )
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok and runtime is not None:
        await runtime.coordinator.async_stop_log_listener()
        await runtime.api.async_close()
        # Clear runtime_data so services and other code that inspects it
        # cannot reach stale coordinator/API objects after teardown.
        entry.runtime_data = None  # type: ignore[assignment]  # cleared after unload

    unload_result: bool = unload_ok
    return unload_result
