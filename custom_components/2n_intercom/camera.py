"""Camera platform for 2N Intercom."""
from __future__ import annotations

import logging
from typing import Any

from typing import TYPE_CHECKING

from homeassistant.components.camera import CameraEntityFeature
from homeassistant.components.mjpeg import MjpegCamera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CameraTransportInfo, TwoNIntercomAPI
from .const import (
    LIVE_VIEW_MODE_MJPEG,
    LIVE_VIEW_MODE_RTSP,
)
from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

# Snapshots are served from the coordinator's cache and the live MJPEG stream
# is proxied by the core MjpegCamera helper, so the camera platform never hits
# the device on async_update — unlimited concurrency is correct here.
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


def _transport_has_live_view(transport_info: CameraTransportInfo) -> bool:
    """Return whether the selected transport yields a live-view URL."""
    if not transport_info.resolved:
        return False
    return transport_info.selected_mode in (LIVE_VIEW_MODE_RTSP, LIVE_VIEW_MODE_MJPEG)


def get_stream_source_for_transport(
    api: TwoNIntercomAPI,
    transport_info: CameraTransportInfo,
) -> str | None:
    """Build a stream source URL for the chosen transport.

    The MJPEG path always returns a credentials-free URL. The camera uses
    the integration's authenticated snapshot path; RTSP keeps creds in
    the URI because that's how the protocol works.
    """
    if not _transport_has_live_view(transport_info):
        return None

    if transport_info.selected_mode == LIVE_VIEW_MODE_RTSP:
        result: str | None = api.get_rtsp_url_with_credentials()
        return result

    if transport_info.selected_mode == LIVE_VIEW_MODE_MJPEG:
        url: str = api.build_mjpeg_url(
            width=transport_info.mjpeg_width,
            height=transport_info.mjpeg_height,
            fps=transport_info.mjpeg_fps,
            source=transport_info.source,
        )
        return url

    return None


def get_supported_features_for_transport(
    transport_info: CameraTransportInfo,
) -> CameraEntityFeature:
    """Return the camera feature flags for the selected transport.

    Only RTSP transports advertise ``STREAM`` — the HA stream component
    (ffmpeg → HLS/WebRTC) requires a stream source URL from
    ``stream_source()``.  MJPEG is served natively by ``MjpegCamera``
    without ffmpeg, so advertising STREAM for it would make the frontend
    try the stream component, get ``None`` from ``stream_source()``, and
    fail with "does not support play stream service".
    """
    if transport_info.resolved and transport_info.selected_mode == LIVE_VIEW_MODE_RTSP:
        return CameraEntityFeature.STREAM
    return CameraEntityFeature(0)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom camera platform."""
    runtime: TwoNIntercomRuntimeData = config_entry.runtime_data
    coordinator: TwoNIntercomCoordinator = runtime.coordinator

    async_add_entities(
        [TwoNIntercomCamera(coordinator, config_entry)],
        True,
    )


class TwoNIntercomCamera(
    CoordinatorEntity[TwoNIntercomCoordinator], MjpegCamera
):
    """Representation of a 2N Intercom camera.

    Inherits from ``MjpegCamera`` so the live MJPEG stream is served
    natively to the frontend without ffmpeg. HTTP credentials stay in the
    integration's request path, not in URLs or the base camera's fetch path.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "camera"
    _attr_is_recording = False
    _attr_motion_detection_enabled = False
    _attr_brand = "2N"
    _attr_model = "IP Intercom"

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialize the camera."""
        api = coordinator.api
        transport_info = coordinator.camera_transport_info

        # The overridden image/stream methods use the integration's auth path.
        mjpeg_url = api.build_mjpeg_url(
            width=transport_info.mjpeg_width,
            height=transport_info.mjpeg_height,
            fps=transport_info.mjpeg_fps,
            source=transport_info.source,
        )
        still_image_url = api.build_snapshot_url(
            width=transport_info.mjpeg_width,
            height=transport_info.mjpeg_height,
            source=transport_info.source,
        )

        CoordinatorEntity.__init__(self, coordinator)
        MjpegCamera.__init__(
            self,
            mjpeg_url=mjpeg_url,
            still_image_url=still_image_url,
            username=None,
            password=None,
            verify_ssl=getattr(api, "verify_ssl", True),
            unique_id=f"{config_entry.entry_id}_camera",
        )

        # ``MjpegCamera.__init__`` unconditionally assigns ``self._attr_name =
        # name`` (defaulting to ``None``). HA's ``Entity._name_internal``
        # short-circuits on ``hasattr(self, "_attr_name")`` and never falls
        # through to the translation_key path, which would otherwise produce
        # the localized "Camera" suffix on top of the device name. Drop the
        # instance attribute so the class-level ``_attr_translation_key``
        # resolution wins.
        try:
            del self._attr_name
        except AttributeError:
            pass

        self._config_entry = config_entry
        self._transport_info = transport_info

        name = config_entry.options.get(
            "name",
            config_entry.data.get("name", "2N Intercom"),
        )
        self._attr_device_info = coordinator.get_device_info(
            config_entry.entry_id, name
        )
        self._attr_supported_features = get_supported_features_for_transport(
            transport_info
        )
        # Set frame interval from configured MJPEG FPS so the still-stream
        # approach produces a comparable frame rate to a native MJPEG proxy.
        if transport_info.mjpeg_fps and transport_info.mjpeg_fps > 0:
            self._attr_frame_interval = 1.0 / transport_info.mjpeg_fps

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose camera capability and transport details."""
        transport_info = self.coordinator.camera_transport_info
        return {
            "live_view_requested_mode": transport_info.requested_mode,
            "live_view_selected_mode": transport_info.selected_mode,
            "live_view_resolved": transport_info.resolved,
            "live_view_available": transport_info.live_view_available,
            "rtsp_available": transport_info.rtsp_available,
            "mjpeg_available": transport_info.mjpeg_available,
            "mjpeg_public_url_available": transport_info.mjpeg_public_url_available,
            "jpeg_snapshot_available": transport_info.jpeg_snapshot_available,
            "camera_source": transport_info.source,
            "mjpeg_width": transport_info.mjpeg_width,
            "mjpeg_height": transport_info.mjpeg_height,
            "mjpeg_fps": transport_info.mjpeg_fps,
            "camera_sources": list(transport_info.capabilities.sources),
            "camera_resolutions": [
                resolution.as_string()
                for resolution in transport_info.capabilities.jpeg_resolutions
            ],
        }

    async def handle_async_mjpeg_stream(self, request: Any) -> Any:
        """Generate MJPEG stream from repeated snapshots.

        ``MjpegCamera`` would normally proxy the raw MJPEG stream from the
        device. That fails when a reverse proxy (e.g. Caddy, nginx) buffers
        the ``multipart/x-mixed-replace`` response — the browser receives
        headers but zero content bytes. Instead we let HA compose its own
        MJPEG boundary stream by polling ``async_camera_image()`` (which
        reads from the coordinator's snapshot cache). This works reliably
        through any proxy or HTTP version.
        """
        return await self.handle_async_still_stream(
            request, self.frame_interval
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image, going through the coordinator's cache."""
        return await self.coordinator.async_get_snapshot(width=width, height=height)

    async def stream_source(self) -> str | None:  # type: ignore[override]
        """Return the stream source for RTSP transports.

        MJPEG transports are served by ``MjpegCamera`` directly without
        ffmpeg, so we only return a stream URL when the resolved transport
        is RTSP. The URL is read from the coordinator's cached transport
        info (resolved once at setup) — no per-call probe.
        """
        transport_info = self.coordinator.camera_transport_info
        if transport_info.selected_mode != LIVE_VIEW_MODE_RTSP:
            return None
        return get_stream_source_for_transport(self.coordinator.api, transport_info)
