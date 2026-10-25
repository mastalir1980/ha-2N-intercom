"""Unit tests for camera stream-source selection."""

from __future__ import annotations

import sys
import types
import unittest
from enum import IntFlag
from unittest.mock import AsyncMock, patch

from _stubs import (
    API_PATH,
    CAMERA_PATH,
    CONST_PATH,
    ensure_package,
    install_api_stubs,
    load_module,
)


def _install_homeassistant_stubs() -> None:
    ha = ensure_package("homeassistant")
    del ha

    camera_module = types.ModuleType("homeassistant.components.camera")

    class Camera:
        def __init__(self) -> None:
            self.hass = None

        async def async_added_to_hass(self) -> None:
            return None

        def async_write_ha_state(self) -> None:
            return None

    class CameraEntityFeature(IntFlag):
        STREAM = 1

    camera_module.Camera = Camera
    camera_module.CameraEntityFeature = CameraEntityFeature
    sys.modules["homeassistant.components.camera"] = camera_module
    ensure_package("homeassistant.components")

    mjpeg_module = types.ModuleType("homeassistant.components.mjpeg")

    class MjpegCamera(Camera):
        def __init__(
            self,
            *,
            mjpeg_url: str,
            still_image_url: str | None = None,
            username: str | None = None,
            password: str | None = None,
            verify_ssl: bool = True,
            unique_id: str | None = None,
            **kwargs,
        ) -> None:
            super().__init__()
            self._mjpeg_url = mjpeg_url
            self._still_image_url = still_image_url
            self._username = username
            self._password = password
            self._verify_ssl = verify_ssl
            self._attr_unique_id = unique_id

        @property
        def frame_interval(self):
            return self._attr_frame_interval

    mjpeg_module.MjpegCamera = MjpegCamera
    sys.modules["homeassistant.components.mjpeg"] = mjpeg_module

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator
            self.hass = getattr(coordinator, "hass", None)

        async def async_added_to_hass(self) -> None:
            return None

        def async_write_ha_state(self) -> None:
            return None

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    ensure_package("homeassistant.helpers")


def load_camera_and_api_modules():
    install_api_stubs()
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    const_module = load_module("custom_components.2n_intercom.const", CONST_PATH)
    api_module = load_module("custom_components.2n_intercom.api", API_PATH)
    coordinator_module = types.ModuleType("custom_components.2n_intercom.coordinator")
    coordinator_module.TwoNIntercomCoordinator = object
    coordinator_module.TwoNIntercomRuntimeData = object
    sys.modules["custom_components.2n_intercom.coordinator"] = coordinator_module
    camera_module = load_module("custom_components.2n_intercom.camera", CAMERA_PATH)
    return camera_module, api_module, const_module


class CameraStreamSourceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for camera stream transport selection."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.camera_module, cls.api_module, cls.const_module = load_camera_and_api_modules()

    def _make_camera_entity(self, transport_info):
        config_entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"name": "Front Door"},
            options={},
        )

        class FakeApi:
            def __init__(self, api_module, chosen_transport):
                self.camera_transport_info = chosen_transport
                self.username = "user"
                self.password = "secret"
                self.verify_ssl = True
                self._api_module = api_module

            async def async_get_camera_transport_info(self, requested_mode):
                del requested_mode
                return self.camera_transport_info

            def get_rtsp_url_with_credentials(self):
                return "rtsp://user:secret@intercom.local:554/h264_stream"

            def build_mjpeg_url(self, *, include_auth=False, **kwargs):
                # Default is no credentials. Camera entity must not opt in.
                assert include_auth is False, "camera must not embed credentials"
                del kwargs
                return (
                    "https://intercom.local:443"
                    "/api/camera/snapshot?source=internal&width=1280&height=960&fps=10"
                )

            def build_snapshot_url(self, *, include_auth=False, **kwargs):
                assert include_auth is False, "camera must not embed credentials"
                del kwargs
                return (
                    "https://intercom.local:443"
                    "/api/camera/snapshot?source=internal&width=1280&height=960"
                )

        class FakeCoordinator:
            def __init__(self, api):
                self.api = api
                self.camera_transport_info = api.camera_transport_info
                self.last_update_success = True
                self.hass = None

            def get_device_info(self, entry_id, name):
                return {"entry_id": entry_id, "name": name}

            async def async_get_snapshot(self, width=None, height=None):
                del width, height
                return b""

        api = FakeApi(self.api_module, transport_info)
        coordinator = FakeCoordinator(api)
        return self.camera_module.TwoNIntercomCamera(coordinator, config_entry), api

    async def test_stream_source_and_supported_features_stay_aligned(self) -> None:
        api = self.api_module.TwoNIntercomAPI(
            host="intercom.local",
            username="user",
            password="secret",
            port=443,
            protocol="https",
            rtsp_username="user",
            rtsp_password="secret",
        )

        mjpeg_public_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_MJPEG,
            resolved=True,
            mjpeg_available=True,
            mjpeg_public_url_available=True,
        )
        mjpeg_auth_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_MJPEG,
            resolved=True,
            mjpeg_available=True,
            mjpeg_public_url_available=False,
        )
        rtsp_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_RTSP,
            resolved=True,
            rtsp_available=True,
        )
        jpeg_only_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_JPEG_ONLY,
            resolved=True,
        )
        unresolved_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_JPEG_ONLY,
            resolved=False,
        )

        # RTSP keeps creds in URL — that is how the protocol works.
        self.assertEqual(
            self.camera_module.get_stream_source_for_transport(api, rtsp_info),
            "rtsp://user:secret@intercom.local:554/h264_stream",
        )
        # MJPEG must NEVER embed credentials regardless of public-URL flag.
        expected_mjpeg = (
            "https://intercom.local:443"
            "/api/camera/snapshot?source=internal&width=1280&height=960&fps=10"
        )
        self.assertEqual(
            self.camera_module.get_stream_source_for_transport(api, mjpeg_public_info),
            expected_mjpeg,
        )
        self.assertEqual(
            self.camera_module.get_stream_source_for_transport(api, mjpeg_auth_info),
            expected_mjpeg,
        )
        self.assertNotIn(
            "user:secret",
            self.camera_module.get_stream_source_for_transport(api, mjpeg_auth_info),
        )
        self.assertIsNone(
            self.camera_module.get_stream_source_for_transport(api, jpeg_only_info)
        )
        self.assertIsNone(
            self.camera_module.get_stream_source_for_transport(api, unresolved_info)
        )

    async def test_camera_entity_contract_for_live_view_states(self) -> None:
        # ``stream_source`` only fires for the RTSP transport. MJPEG is
        # served by ``MjpegCamera`` directly without ffmpeg, so a None
        # stream source there is correct (and a key part of H1: the
        # MJPEG URL never carries credentials anywhere).
        cases = [
            (
                "unresolved",
                self.api_module.CameraTransportInfo(
                    selected_mode=self.const_module.LIVE_VIEW_MODE_JPEG_ONLY,
                    resolved=False,
                ),
                0,
                None,
            ),
            (
                "mjpeg-public",
                self.api_module.CameraTransportInfo(
                    selected_mode=self.const_module.LIVE_VIEW_MODE_MJPEG,
                    resolved=True,
                    mjpeg_available=True,
                    mjpeg_public_url_available=True,
                ),
                0,
                None,
            ),
            (
                "rtsp",
                self.api_module.CameraTransportInfo(
                    selected_mode=self.const_module.LIVE_VIEW_MODE_RTSP,
                    resolved=True,
                    rtsp_available=True,
                ),
                self.camera_module.CameraEntityFeature.STREAM,
                "rtsp://user:secret@intercom.local:554/h264_stream",
            ),
            (
                "jpeg-only",
                self.api_module.CameraTransportInfo(
                    selected_mode=self.const_module.LIVE_VIEW_MODE_JPEG_ONLY,
                    resolved=True,
                ),
                0,
                None,
            ),
        ]

        for _, transport_info, expected_features, expected_source in cases:
            camera_entity, _ = self._make_camera_entity(transport_info)
            self.assertEqual(camera_entity._attr_supported_features, expected_features)
            self.assertIsInstance(
                camera_entity._attr_supported_features, self.camera_module.CameraEntityFeature
            )
            if expected_features:
                self.assertIn(
                    self.camera_module.CameraEntityFeature.STREAM,
                    camera_entity._attr_supported_features,
                )
            else:
                self.assertNotIn(
                    self.camera_module.CameraEntityFeature.STREAM,
                    camera_entity._attr_supported_features,
                )
            self.assertEqual(await camera_entity.stream_source(), expected_source)

    async def test_camera_entity_does_not_pass_api_credentials_to_mjpeg_camera(self) -> None:
        """Only the integration request path may access HTTP API credentials."""
        transport_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_MJPEG,
            resolved=True,
            mjpeg_available=True,
            mjpeg_public_url_available=False,
        )
        camera_entity, _ = self._make_camera_entity(transport_info)

        self.assertNotIn("user:secret", camera_entity._mjpeg_url)
        self.assertNotIn("user:secret", camera_entity._still_image_url or "")
        self.assertIsNone(camera_entity._username)
        self.assertIsNone(camera_entity._password)

    async def test_snapshot_and_mjpeg_stream_use_coordinator_snapshot_path(self) -> None:
        camera_entity, _ = self._make_camera_entity(self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_MJPEG,
            resolved=True,
            mjpeg_available=True,
        ))
        jpeg = b"\xff\xd8snapshot\xff\xd9"
        camera_entity.coordinator.async_get_snapshot = AsyncMock(return_value=jpeg)
        self.assertEqual(
            await camera_entity.async_camera_image(width=640, height=480), jpeg,
        )
        camera_entity.coordinator.async_get_snapshot.assert_awaited_once_with(
            width=640, height=480,
        )

        async def still_stream(request, interval):
            self.assertIs(request, stream_request)
            self.assertEqual(interval, 0.1)
            return await camera_entity.async_camera_image()

        stream_request = object()
        with patch.object(
            camera_entity, "handle_async_still_stream",
            AsyncMock(side_effect=still_stream), create=True,
        ) as stream:
            self.assertEqual(
                await camera_entity.handle_async_mjpeg_stream(stream_request), jpeg,
            )
            stream.assert_awaited_once_with(stream_request, camera_entity.frame_interval)
        camera_entity.coordinator.async_get_snapshot.assert_awaited_with(
            width=None, height=None,
        )

    async def test_camera_entity_deletes_attr_name_set_by_mjpeg_camera(self) -> None:
        """MjpegCamera.__init__ unconditionally sets self._attr_name = None,
        which short-circuits HA's Entity._name_internal resolution and
        prevents the translation_key 'camera' from producing a localized
        suffix. The integration must delete _attr_name after MjpegCamera
        init so the class-level _attr_translation_key wins."""
        transport_info = self.api_module.CameraTransportInfo(
            selected_mode=self.const_module.LIVE_VIEW_MODE_MJPEG,
            resolved=True,
            mjpeg_available=True,
        )
        camera_entity, _ = self._make_camera_entity(transport_info)

        # _attr_name must NOT exist as an instance attribute
        self.assertFalse(
            hasattr(camera_entity, "_attr_name")
            and "_attr_name" in camera_entity.__dict__,
            "_attr_name instance attribute was not deleted after MjpegCamera init",
        )
        # _attr_translation_key must be set at class level
        self.assertEqual(camera_entity._attr_translation_key, "camera")


if __name__ == "__main__":
    unittest.main()
