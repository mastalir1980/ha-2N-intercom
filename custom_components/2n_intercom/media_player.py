"""Speaker media player for 2N Intercom.

Plays audio on the intercom speaker over the RTSP audio backchannel (see
``backchannel.py``). The entity is created only when RTSP credentials are
configured and the device offers a backchannel track. Home Assistant's
ffmpeg transcodes the source to the G.711 codec the device asked for.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .backchannel import (
    FRAME_BYTES,
    REASON_AUTH,
    REASON_CONNECTION,
    REASON_UNSUPPORTED,
    BackchannelError,
    BackchannelTrack,
    RtspBackchannelClient,
)
from .const import DOMAIN
from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData
from .entity import TwoNIntercomEntity

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

# One playback at a time: the device has one speaker.
PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)

# Time ffmpeg gets to deliver the first audio frame before the source is
# treated as unplayable.
FFMPEG_START_TIMEOUT = 15.0
# ffmpeg may only open network sources: play_media must not become a way to
# read local files of the Home Assistant host.
FFMPEG_PROTOCOL_WHITELIST = "http,https,tcp,tls,crypto"

_ERROR_KEYS = {
    REASON_AUTH: "speaker_auth_failed",
    REASON_UNSUPPORTED: "speaker_backchannel_unsupported",
    REASON_CONNECTION: "speaker_connection_failed",
}


def _create_client(
    coordinator: TwoNIntercomCoordinator, url: str
) -> RtspBackchannelClient:
    """Build a backchannel client from the stored RTSP credentials."""
    api = coordinator.api
    host, port, _ = api.get_rtsp_backchannel_endpoint()
    return RtspBackchannelClient(
        host, port, url, api.rtsp_username or "", api.rtsp_password or ""
    )


async def _async_find_backchannel(
    coordinator: TwoNIntercomCoordinator,
) -> tuple[str, BackchannelTrack]:
    """Return the first RTSP URL on which the device offers the backchannel.

    Raises the ``BackchannelError`` of the last URL tried; a failure other
    than "unsupported" (credentials, network) ends the search at once.
    """
    _, _, urls = coordinator.api.get_rtsp_backchannel_endpoint()
    last_error = BackchannelError(REASON_UNSUPPORTED, "No RTSP URL to try")
    for url in urls:
        client = _create_client(coordinator, url)
        try:
            return url, await client.async_describe()
        except BackchannelError as err:
            if err.reason != REASON_UNSUPPORTED:
                raise
            last_error = err
        finally:
            await client.async_close()
    raise last_error


def _ffmpeg_binary(hass: HomeAssistant) -> str:
    """Return the ffmpeg binary configured in Home Assistant."""
    try:
        from homeassistant.components.ffmpeg import (  # noqa: PLC0415
            get_ffmpeg_manager,
        )

        return str(get_ffmpeg_manager(hass).binary)
    except Exception:  # pylint: disable=broad-except
        # The ffmpeg integration is optional (after_dependencies); without
        # it fall back to the binary on PATH.
        _LOGGER.debug("ffmpeg integration not loaded; using ffmpeg from PATH")
        return "ffmpeg"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the speaker when the device offers an audio backchannel."""
    runtime: TwoNIntercomRuntimeData = config_entry.runtime_data
    coordinator = runtime.coordinator
    api = coordinator.api

    if not api.rtsp_username or not api.rtsp_password:
        return
    if not coordinator.camera_transport_info.rtsp_available:
        _LOGGER.debug("Speaker not created: RTSP is not available")
        return

    try:
        url, track = await _async_find_backchannel(coordinator)
    except BackchannelError as err:
        if err.reason == REASON_UNSUPPORTED:
            _LOGGER.debug("Speaker not created: %s", err)
        else:
            _LOGGER.warning(
                "Speaker not created, the audio backchannel probe failed: %s. "
                "Reload the integration to retry",
                err,
            )
        return

    _LOGGER.debug("Audio backchannel available (codec %s)", track.codec)
    async_add_entities([TwoNIntercomSpeaker(coordinator, config_entry, url)])


class TwoNIntercomSpeaker(TwoNIntercomEntity, MediaPlayerEntity):  # type: ignore[misc]
    """The intercom speaker, fed over the RTSP audio backchannel."""

    _attr_translation_key = "speaker"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
        backchannel_url: str,
    ) -> None:
        """Initialize the speaker for the RTSP URL found at setup."""
        super().__init__(coordinator, config_entry)
        self._backchannel_url = backchannel_url
        self._attr_unique_id = f"{config_entry.entry_id}_speaker"
        self._attr_state = MediaPlayerState.IDLE
        self._playback_task: asyncio.Task[None] | None = None
        self._active: (
            tuple[RtspBackchannelClient, asyncio.subprocess.Process] | None
        ) = None

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse audio from the media sources."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a URL or media-source item on the intercom speaker.

        Returns once the first audio is decoded and the RTSP session plays;
        the rest is streamed in a background task.
        """
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = play_item.url
        url = async_process_play_media_url(self.hass, media_id)
        if urlsplit(url).scheme not in ("http", "https"):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="speaker_invalid_media",
                translation_placeholders={},
            )

        await self._async_stop_playback()

        client: RtspBackchannelClient | None = None
        process: asyncio.subprocess.Process | None = None
        try:
            client = _create_client(self.coordinator, self._backchannel_url)
            track = await client.async_describe()
            process, first_frame = await self._async_start_ffmpeg(url, track)
            await client.async_start()
        except BackchannelError as err:
            await self._async_cleanup(client, process)
            _LOGGER.warning("Cannot play on the intercom speaker: %s", err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=_ERROR_KEYS[err.reason],
                translation_placeholders={},
            ) from err
        except BaseException:
            await self._async_cleanup(client, process)
            raise

        self._active = (client, process)
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        self._playback_task = self._config_entry.async_create_background_task(
            self.hass,
            self._async_stream(client, process, first_frame),
            name=f"{DOMAIN}_speaker_{self._config_entry.entry_id}",
        )

    async def async_media_stop(self) -> None:
        """Stop the running playback."""
        await self._async_stop_playback()

    async def async_will_remove_from_hass(self) -> None:
        """Stop playback when the entity goes away."""
        await self._async_stop_playback()
        await super().async_will_remove_from_hass()

    async def _async_start_ffmpeg(
        self, url: str, track: BackchannelTrack
    ) -> tuple[asyncio.subprocess.Process, bytes]:
        """Start ffmpeg and wait for the first audio frame."""
        try:
            process = await asyncio.create_subprocess_exec(
                _ffmpeg_binary(self.hass),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                FFMPEG_PROTOCOL_WHITELIST,
                "-i",
                url,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-f",
                track.ffmpeg_format,
                "pipe:1",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as err:
            _LOGGER.warning("Cannot start ffmpeg: %s", type(err).__name__)
            raise self._media_error() from err

        assert process.stdout is not None
        try:
            first_frame = await asyncio.wait_for(
                process.stdout.readexactly(FRAME_BYTES), timeout=FFMPEG_START_TIMEOUT
            )
        except (asyncio.IncompleteReadError, asyncio.TimeoutError) as err:
            await self._async_cleanup(None, process)
            # The media URL may carry a signed token, so it is not logged.
            _LOGGER.warning(
                "ffmpeg produced no audio for the requested media (exit code %s)",
                process.returncode,
            )
            raise self._media_error() from err
        except BaseException:
            await self._async_cleanup(None, process)
            raise
        return process, first_frame

    @staticmethod
    def _media_error() -> HomeAssistantError:
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="speaker_media_failed",
            translation_placeholders={},
        )

    async def _async_stream(
        self,
        client: RtspBackchannelClient,
        process: asyncio.subprocess.Process,
        first_frame: bytes,
    ) -> None:
        """Feed ffmpeg's output to the device until the source ends."""
        assert process.stdout is not None
        try:
            frames = await client.async_send_stream(process.stdout, first_frame)
            _LOGGER.debug("Speaker playback finished (%d frames)", frames)
        except BackchannelError as err:
            _LOGGER.warning("Speaker playback interrupted: %s", err)
        finally:
            if self._playback_task is asyncio.current_task():
                self._playback_task = None
            await asyncio.shield(self._async_finish(client, process))

    async def _async_finish(
        self, client: RtspBackchannelClient, process: asyncio.subprocess.Process
    ) -> None:
        """Release one playback and report idle if it was the current one."""
        await self._async_cleanup(client, process)
        if self._active == (client, process):
            self._active = None
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()

    async def _async_stop_playback(self) -> None:
        """Cancel the background stream and release its resources."""
        task, self._playback_task = self._playback_task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # A task cancelled before its first step never runs its cleanup.
        if self._active is not None:
            await self._async_finish(*self._active)

    @staticmethod
    async def _async_cleanup(
        client: RtspBackchannelClient | None,
        process: asyncio.subprocess.Process | None,
    ) -> None:
        """Close the RTSP session and make sure ffmpeg is gone."""
        if client is not None:
            await client.async_close()
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
