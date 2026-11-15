"""Unit tests for the speaker media player (fake RTSP server, fake ffmpeg)."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from enum import IntFlag
from unittest.mock import AsyncMock, patch

from _rtsp_fake import SDP_WITHOUT_BACKCHANNEL, FakeRtspServer
from _stubs import CONST_PATH, ENTITY_PATH, INTEGRATION_DIR, ensure_package, load_module

MEDIA_PLAYER_PATH = INTEGRATION_DIR / "media_player.py"
BACKCHANNEL_PATH = INTEGRATION_DIR / "backchannel.py"
PACKAGE = "custom_components.2n_intercom"


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")
    ensure_package("homeassistant.components")
    ensure_package("homeassistant.helpers")

    exceptions = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        def __init__(
            self, *, translation_domain, translation_key, translation_placeholders
        ) -> None:
            super().__init__(translation_key)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    exceptions.HomeAssistantError = HomeAssistantError
    sys.modules["homeassistant.exceptions"] = exceptions

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda fn: fn  # noqa: E731
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
            self.hass = coordinator.hass
            self.states: list[str] = []

        def async_write_ha_state(self) -> None:
            self.states.append(self._attr_state)

        async def async_will_remove_from_hass(self) -> None:
            return None

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    media_source = types.ModuleType("homeassistant.components.media_source")
    media_source.is_media_source_id = lambda media_id: media_id.startswith(
        "media-source://"
    )
    media_source.async_resolve_media = AsyncMock()
    media_source.async_browse_media = AsyncMock(return_value="browse-result")
    sys.modules["homeassistant.components.media_source"] = media_source
    sys.modules["homeassistant.components"].media_source = media_source

    media_player = types.ModuleType("homeassistant.components.media_player")

    class MediaPlayerEntityFeature(IntFlag):
        STOP = 4096
        PLAY_MEDIA = 512
        BROWSE_MEDIA = 131072
        MEDIA_ANNOUNCE = 1048576

    class MediaPlayerState:
        IDLE = "idle"
        PLAYING = "playing"

    class MediaPlayerDeviceClass:
        SPEAKER = "speaker"

    class MediaType:
        MUSIC = "music"

    class MediaPlayerEntity:
        entity_id = "media_player.front_door_speaker"

    def async_process_play_media_url(hass, media_id):
        if media_id.startswith("/"):
            return f"http://ha.local:8123{media_id}"
        return media_id

    media_player.BrowseMedia = object
    media_player.MediaPlayerDeviceClass = MediaPlayerDeviceClass
    media_player.MediaPlayerEntity = MediaPlayerEntity
    media_player.MediaPlayerEntityFeature = MediaPlayerEntityFeature
    media_player.MediaPlayerState = MediaPlayerState
    media_player.MediaType = MediaType
    media_player.async_process_play_media_url = async_process_play_media_url
    sys.modules["homeassistant.components.media_player"] = media_player


def load_media_player_module():
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package(PACKAGE)
    load_module(f"{PACKAGE}.const", CONST_PATH)
    coordinator_module = types.ModuleType(f"{PACKAGE}.coordinator")
    coordinator_module.TwoNIntercomCoordinator = object
    coordinator_module.TwoNIntercomRuntimeData = object
    sys.modules[f"{PACKAGE}.coordinator"] = coordinator_module
    load_module(f"{PACKAGE}.entity", ENTITY_PATH)
    backchannel = load_module(f"{PACKAGE}.backchannel", BACKCHANNEL_PATH)
    return load_module(f"{PACKAGE}.media_player", MEDIA_PLAYER_PATH), backchannel


class FakeProcess:
    """Stands in for ffmpeg: stdout delivers the prepared audio."""

    def __init__(self, audio: bytes, *, hang: bool = False) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(audio)
        if not hang:
            self.stdout.feed_eof()
        self.returncode: int | None = None if (hang or audio) else 1
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.stdout.feed_eof()

    async def wait(self) -> int:
        return self.returncode or 0


class FakeCoordinator:
    def __init__(self, server: FakeRtspServer | None, *, password=None, rtsp=True):
        self.hass = types.SimpleNamespace()
        self.last_update_success = True
        port = server.port if server else 1
        self.api = types.SimpleNamespace(
            rtsp_username=server.username if server else None,
            rtsp_password=(password or server.password) if server else None,
            get_rtsp_backchannel_endpoint=lambda: (
                "127.0.0.1",
                port,
                [
                    f"rtsp://127.0.0.1:{port}"
                    "/onvif/media?transport=unicast&profile=profile_h264_hq",
                    f"rtsp://127.0.0.1:{port}/h264_stream",
                ],
            ),
        )
        self.camera_transport_info = types.SimpleNamespace(rtsp_available=rtsp)
        backchannel = sys.modules[f"{PACKAGE}.backchannel"]
        self.backchannel_probe = backchannel.BackchannelProbe(self.api)

    def get_device_info(self, entry_id, name):
        return {"entry_id": entry_id, "name": name}


class FakeConfigEntry:
    def __init__(self, coordinator) -> None:
        self.entry_id = "entry-1"
        self.data = {"name": "Front Door"}
        self.options = {}
        self.runtime_data = types.SimpleNamespace(coordinator=coordinator)
        self.background_tasks: list[tuple[asyncio.Task, str]] = []

    def async_create_background_task(self, hass, target, name):
        task = asyncio.ensure_future(target)
        self.background_tasks.append((task, name))
        return task


class SpeakerTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module, cls.backchannel = load_media_player_module()

    def setUp(self) -> None:
        original = self.backchannel.FRAME_SECONDS
        self.backchannel.FRAME_SECONDS = 0.0005
        self.addCleanup(setattr, self.backchannel, "FRAME_SECONDS", original)
        self.spawned: list[tuple[tuple, FakeProcess]] = []
        media_source = sys.modules["homeassistant.components.media_source"]
        media_source.async_resolve_media.reset_mock()

    def _ffmpeg(self, audio: bytes, *, hang: bool = False):
        async def create_subprocess_exec(*args, **kwargs):
            process = FakeProcess(audio, hang=hang)
            self.spawned.append((args, process))
            return process

        return patch.object(
            self.module.asyncio, "create_subprocess_exec", create_subprocess_exec
        )

    async def _setup(self, coordinator):
        entry = FakeConfigEntry(coordinator)
        added: list = []
        await self.module.async_setup_entry(
            coordinator.hass, entry, lambda entities: added.extend(entities)
        )
        return entry, added

    async def _entity(self, server, **kwargs):
        coordinator = FakeCoordinator(server, **kwargs)
        entry = FakeConfigEntry(coordinator)
        url = coordinator.api.get_rtsp_backchannel_endpoint()[2][0]
        return self.module.TwoNIntercomSpeaker(coordinator, entry, url), entry

    async def _finish(self, entry) -> None:
        for task, _ in entry.background_tasks:
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)

    async def test_setup_creates_speaker_when_backchannel_is_offered(self) -> None:
        async with FakeRtspServer() as server:
            _, added = await self._setup(FakeCoordinator(server))
        self.assertEqual(len(added), 1)
        entity = added[0]
        self.assertIsInstance(entity, self.module.TwoNIntercomEntity)
        self.assertEqual(entity._attr_unique_id, "entry-1_speaker")
        self.assertEqual(entity._attr_translation_key, "speaker")
        self.assertEqual(entity._attr_device_class, "speaker")
        self.assertEqual(entity._attr_state, "idle")
        self.assertTrue(entity._attr_has_entity_name)
        features = self.module.MediaPlayerEntityFeature
        self.assertEqual(
            entity._attr_supported_features,
            features.PLAY_MEDIA
            | features.STOP
            | features.MEDIA_ANNOUNCE
            | features.BROWSE_MEDIA,
        )
        # The probe only describes the stream; it never opens a session.
        self.assertEqual(server.methods(), ["DESCRIBE", "DESCRIBE"])
        self.assertEqual(server.packets, [])

    async def test_onvif_media_url_is_used_when_the_classic_path_refuses(self) -> None:
        """Firmware 3.x: 551 on /h264_stream, backchannel on the ONVIF URL."""
        async with FakeRtspServer(onvif_only=True) as server:
            entry, added = await self._setup(FakeCoordinator(server))
            self.assertEqual(len(added), 1)
            self.assertEqual(added[0]._backchannel_url, server.onvif_url)
            self.assertTrue(all(uri == server.onvif_url for _, uri, _ in server.requests))
            server.requests.clear()

            with self._ffmpeg(b"\x00" * 320):
                await added[0].async_play_media("music", "http://media.example/a.mp3")
                await self._finish(entry)
            await asyncio.wait_for(server.torn_down.wait(), timeout=2)
            uris = {method: uri for method, uri, _ in server.requests}
            self.assertEqual(uris["DESCRIBE"], server.onvif_url)
            self.assertEqual(
                uris["SETUP"], f"rtsp://127.0.0.1:{server.port}/onvif/media/audioback"
            )
            self.assertEqual(uris["PLAY"], server.onvif_url)
            self.assertEqual(uris["TEARDOWN"], server.onvif_url)
            self.assertEqual(len(server.packets), 2 + 10)

    async def test_classic_path_is_the_fallback(self) -> None:
        """A device that knows the backchannel only on /h264_stream still works."""

        class ClassicOnly(FakeRtspServer):
            def _answer(self, method, uri, headers):
                if "/onvif/media" in uri and "authorization" in headers:
                    return f"RTSP/1.0 404 Not Found\r\nCSeq: {headers['cseq']}\r\n\r\n"
                return super()._answer(method, uri, headers)

        async with ClassicOnly() as server:
            _, added = await self._setup(FakeCoordinator(server))
            self.assertEqual(len(added), 1)
            self.assertEqual(added[0]._backchannel_url, server.url)

    async def test_setup_creates_nothing_without_a_usable_backchannel(self) -> None:
        _, added = await self._setup(FakeCoordinator(None))
        self.assertEqual(added, [])

        async with FakeRtspServer() as server:
            _, added = await self._setup(FakeCoordinator(server, rtsp=False))
            self.assertEqual(added, [])
            self.assertEqual(server.requests, [])

        async with FakeRtspServer(sdp=SDP_WITHOUT_BACKCHANNEL) as server:
            _, added = await self._setup(FakeCoordinator(server))
            self.assertEqual(added, [])

        async with FakeRtspServer() as server:
            with self.assertLogs(self.module._LOGGER, level="WARNING") as logs:
                _, added = await self._setup(
                    FakeCoordinator(server, password="wrong-pass-123")
                )
            self.assertEqual(added, [])
            self.assertNotIn("wrong-pass-123", "\n".join(logs.output))

    async def test_play_media_streams_transcoded_audio_and_returns_to_idle(self) -> None:
        audio = bytes(range(200)) * 4  # 800 bytes = 5 frames
        async with FakeRtspServer() as server:
            entity, entry = await self._entity(server)
            with self._ffmpeg(audio):
                await entity.async_play_media(
                    "music", "http://media.example/bell.mp3", announce=True
                )
                self.assertEqual(entity._attr_state, "playing")
                await self._finish(entry)
            await asyncio.wait_for(server.torn_down.wait(), timeout=2)

        self.assertEqual(entity.states, ["playing", "idle"])
        self.assertEqual(entity._attr_state, "idle")
        self.assertIsNone(entity._playback_task)
        self.assertEqual(
            server.methods(), ["DESCRIBE", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN"]
        )
        sent = b"".join(packet[12:] for _, packet in server.packets)
        self.assertEqual(sent[:800], audio)

        (args, process), = self.spawned
        self.assertEqual(args[0], "ffmpeg")
        self.assertEqual(args[args.index("-i") + 1], "http://media.example/bell.mp3")
        self.assertEqual(args[args.index("-f") + 1], "mulaw")
        self.assertEqual(args[args.index("-ar") + 1], "8000")
        self.assertEqual(args[args.index("-ac") + 1], "1")
        self.assertEqual(
            args[args.index("-protocol_whitelist") + 1], "http,https,tcp,tls,crypto"
        )
        self.assertLess(args.index("-protocol_whitelist"), args.index("-i"))
        self.assertEqual(entry.background_tasks[0][1], "2n_intercom_speaker_entry-1")

    async def test_media_source_and_relative_urls_are_resolved(self) -> None:
        media_source = sys.modules["homeassistant.components.media_source"]
        media_source.async_resolve_media.return_value = types.SimpleNamespace(
            url="/api/tts_proxy/hello.mp3"
        )
        async with FakeRtspServer() as server:
            entity, entry = await self._entity(server)
            with self._ffmpeg(b"\x00" * 160):
                await entity.async_play_media(
                    "music", "media-source://tts/cloud?message=hello"
                )
                await self._finish(entry)
        media_source.async_resolve_media.assert_awaited_once_with(
            entity.hass,
            "media-source://tts/cloud?message=hello",
            "media_player.front_door_speaker",
        )
        args = self.spawned[0][0]
        self.assertEqual(
            args[args.index("-i") + 1], "http://ha.local:8123/api/tts_proxy/hello.mp3"
        )

    async def test_stop_and_second_play_end_the_running_playback(self) -> None:
        self.backchannel.FRAME_SECONDS = 0.002
        async with FakeRtspServer() as server:
            entity, entry = await self._entity(server)
            with self._ffmpeg(b"\x00" * 160 * 3, hang=True):
                await entity.async_play_media("music", "http://media.example/a.mp3")
                first_task = entity._playback_task
                await entity.async_play_media("music", "http://media.example/b.mp3")
                self.assertTrue(first_task.done())
                self.assertTrue(self.spawned[0][1].killed)
                self.assertEqual(entity._attr_state, "playing")

                await entity.async_media_stop()
            self.assertEqual(entity._attr_state, "idle")
            self.assertIsNone(entity._playback_task)
            self.assertTrue(self.spawned[1][1].killed)
            # The client does not wait for the TEARDOWN answers.
            for _ in range(200):
                if server.methods().count("TEARDOWN") == 2:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(server.methods().count("TEARDOWN"), 2)
            self.assertEqual(server.methods().count("PLAY"), 2)
            # Stopping again, or removing the entity, is harmless.
            await entity.async_media_stop()
            await entity.async_will_remove_from_hass()

    async def test_rejected_credentials_raise_a_translated_error(self) -> None:
        async with FakeRtspServer() as server:
            entity, entry = await self._entity(server, password="wrong-pass-123")
            with self._ffmpeg(b"\x00" * 160), self.assertLogs(
                self.module._LOGGER, level="DEBUG"
            ) as logs:
                with self.assertRaises(self.module.HomeAssistantError) as raised:
                    await entity.async_play_media(
                        "music", "http://media.example/a.mp3"
                    )
        self.assertEqual(raised.exception.translation_key, "speaker_auth_failed")
        self.assertEqual(raised.exception.translation_domain, "2n_intercom")
        self.assertEqual(entity._attr_state, "idle")
        self.assertEqual(self.spawned, [])
        self.assertEqual(entry.background_tasks, [])
        self.assertNotIn("wrong-pass-123", "\n".join(logs.output))

    async def test_missing_backchannel_and_unreachable_device(self) -> None:
        async with FakeRtspServer(sdp=SDP_WITHOUT_BACKCHANNEL) as server:
            entity, _ = await self._entity(server)
            with self._ffmpeg(b"\x00" * 160), self.assertLogs(
                self.module._LOGGER, level="WARNING"
            ):
                with self.assertRaises(self.module.HomeAssistantError) as raised:
                    await entity.async_play_media("music", "http://media.example/a")
            self.assertEqual(
                raised.exception.translation_key, "speaker_backchannel_unsupported"
            )
            closed_entity, _ = await self._entity(server)
        with self._ffmpeg(b"\x00" * 160), self.assertLogs(
            self.module._LOGGER, level="WARNING"
        ):
            with self.assertRaises(self.module.HomeAssistantError) as raised:
                await closed_entity.async_play_media("music", "http://media.example/a")
        self.assertEqual(raised.exception.translation_key, "speaker_connection_failed")
        self.assertEqual(self.spawned, [])

    async def test_undecodable_media_closes_the_rtsp_connection(self) -> None:
        async with FakeRtspServer() as server:
            entity, entry = await self._entity(server)
            with self._ffmpeg(b""), self.assertLogs(
                self.module._LOGGER, level="WARNING"
            ) as logs:
                with self.assertRaises(self.module.HomeAssistantError) as raised:
                    await entity.async_play_media(
                        "music", "http://media.example/a.mp3?authSig=tok-456"
                    )
            self.assertEqual(raised.exception.translation_key, "speaker_media_failed")
            self.assertEqual(server.methods(), ["DESCRIBE", "DESCRIBE"])
        self.assertEqual(entity._attr_state, "idle")
        self.assertEqual(entry.background_tasks, [])
        self.assertNotIn("tok-456", "\n".join(logs.output))

    async def test_only_http_sources_reach_ffmpeg(self) -> None:
        async with FakeRtspServer() as server:
            entity, _ = await self._entity(server)
            for media_id in ("file:///config/secrets.yaml", "concat:/etc/passwd", "x"):
                with self.subTest(media_id=media_id), self._ffmpeg(b"\x00" * 160):
                    with self.assertRaises(self.module.HomeAssistantError) as raised:
                        await entity.async_play_media("music", media_id)
                    self.assertEqual(
                        raised.exception.translation_key, "speaker_invalid_media"
                    )
            self.assertEqual(server.requests, [])
        self.assertEqual(self.spawned, [])

    async def test_lost_connection_ends_playback_idle(self) -> None:
        self.backchannel.FRAME_SECONDS = 0.005
        async with FakeRtspServer(close_after_packets=2) as server:
            entity, entry = await self._entity(server)
            with self._ffmpeg(b"\x00" * 160 * 400), self.assertLogs(
                self.module._LOGGER, level="WARNING"
            ) as logs:
                await entity.async_play_media("music", "http://media.example/a.mp3")
                await self._finish(entry)
        self.assertIn("interrupted", "\n".join(logs.output))
        self.assertEqual(entity.states, ["playing", "idle"])
        self.assertTrue(self.spawned[0][1].killed)

    async def test_browse_media_offers_audio_only(self) -> None:
        media_source = sys.modules["homeassistant.components.media_source"]
        entity, _ = await self._entity(None)
        result = await entity.async_browse_media("music", "media-source://x")
        self.assertEqual(result, "browse-result")
        args, kwargs = media_source.async_browse_media.await_args
        self.assertEqual(args, (entity.hass, "media-source://x"))
        content_filter = kwargs["content_filter"]
        self.assertTrue(content_filter(types.SimpleNamespace(media_content_type="audio/mpeg")))
        self.assertFalse(content_filter(types.SimpleNamespace(media_content_type="video/mp4")))


if __name__ == "__main__":
    unittest.main()
