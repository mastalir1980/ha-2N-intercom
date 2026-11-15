"""RTSP audio backchannel client for 2N intercoms.

Implements the client side of the ONVIF Streaming Specification chapter
"Audio backchannel": every request carries ``Require:
www.onvif.org/ver20/backchannel``, the DESCRIBE answer then contains an
extra audio media section marked ``a=sendonly`` and the client sends RTP
packets for it interleaved on the RTSP TCP connection.

The module has no Home Assistant imports so it can be unit-tested against a
fake RTSP server. The password is only used to compute Digest responses; it
is never put into a URL, a log record or an exception message.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import struct
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

BACKCHANNEL_REQUIRE = "www.onvif.org/ver20/backchannel"
USER_AGENT = "HomeAssistant-2NIntercom"

RTSP_TIMEOUT = 5.0
SAMPLE_RATE = 8000
FRAME_SECONDS = 0.02
FRAME_BYTES = int(SAMPLE_RATE * FRAME_SECONDS)
# Silence appended after the last frame so a jitter buffer on the device
# does not cut the end of the clip when the session is torn down.
TRAILING_SILENCE_FRAMES = 10
DEFAULT_SESSION_TIMEOUT = 60.0
_MAX_HEADER_BYTES = 16384
_MAX_BODY_BYTES = 65536

REASON_AUTH = "auth"
REASON_UNSUPPORTED = "unsupported"
REASON_CONNECTION = "connection"

# codec -> (ffmpeg raw output format, byte value of digital silence)
SUPPORTED_CODECS: dict[str, tuple[str, int]] = {
    "PCMU": ("mulaw", 0xFF),
    "PCMA": ("alaw", 0xD5),
}
_STATIC_PAYLOAD_TYPES = {0: ("PCMU", 8000), 8: ("PCMA", 8000)}

_DIGEST_UNSAFE_RE = re.compile(r'["\r\n]')


class BackchannelError(Exception):
    """Backchannel failure; ``reason`` is one of the ``REASON_*`` values."""

    def __init__(self, reason: str, message: str) -> None:
        """Store the machine-readable reason next to the message."""
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class BackchannelTrack:
    """The audio track the device accepts from the client."""

    control: str
    payload_type: int
    codec: str

    @property
    def ffmpeg_format(self) -> str:
        """Return the raw ffmpeg output format for this codec."""
        return SUPPORTED_CODECS[self.codec][0]

    @property
    def silence(self) -> bytes:
        """Return one frame of digital silence."""
        return bytes([SUPPORTED_CODECS[self.codec][1]]) * FRAME_BYTES


@dataclass
class _Response:
    status: int
    reason: str
    headers: dict[str, list[str]]
    body: bytes

    def header(self, name: str) -> str | None:
        values = self.headers.get(name.lower())
        return values[0] if values else None


def _resolve_control(control: str, base_url: str) -> str:
    """Resolve an SDP ``a=control`` value against the content base."""
    if control == "*" or not control:
        return base_url
    if control.lower().startswith(("rtsp://", "rtsps://")):
        return control
    return f"{base_url.rstrip('/')}/{control.lstrip('/')}"


def parse_backchannel_track(sdp: str, base_url: str) -> BackchannelTrack | None:
    """Return the first usable ``sendonly`` audio track of an SDP, if any."""
    sections: list[list[str]] = []
    for raw_line in sdp.splitlines():
        line = raw_line.strip()
        if line.startswith("m="):
            sections.append([line])
        elif sections:
            sections[-1].append(line)

    for section in sections:
        media = section[0][2:].split()
        if len(media) < 4 or media[0] != "audio":
            continue
        if "a=sendonly" not in section:
            continue

        rtpmap: dict[int, tuple[str, int]] = dict(_STATIC_PAYLOAD_TYPES)
        control = ""
        for line in section[1:]:
            if line.startswith("a=control:"):
                control = line[len("a=control:"):].strip()
                continue
            match = re.match(r"a=rtpmap:(\d+)\s+([^/\s]+)/(\d+)", line)
            if match:
                rtpmap[int(match.group(1))] = (
                    match.group(2).upper(),
                    int(match.group(3)),
                )

        for token in media[3:]:
            if not token.isdigit():
                continue
            payload_type = int(token)
            codec, rate = rtpmap.get(payload_type, ("", 0))
            if codec in SUPPORTED_CODECS and rate == SAMPLE_RATE:
                return BackchannelTrack(
                    control=_resolve_control(control, base_url),
                    payload_type=payload_type,
                    codec=codec,
                )
    return None


class _DigestAuth:
    """RFC 2617 Digest (MD5) with an increasing nonce count."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._realm: str | None = None
        self._nonce: str | None = None
        self._opaque: str | None = None
        self._qop: str | None = None
        self._nonce_count = 0

    def update(self, challenges: list[str]) -> bool:
        """Adopt a Digest challenge; return False when none is usable."""
        for challenge in challenges:
            if not challenge.lower().startswith("digest"):
                continue
            params = {
                key.lower(): quoted if quoted or not bare else bare
                for key, quoted, bare in re.findall(
                    r'(\w+)\s*=\s*(?:"((?:\\.|[^"\\])*)"|([^,\s]+))', challenge
                )
            }
            algorithm = params.get("algorithm", "MD5").upper()
            realm = params.get("realm")
            nonce = params.get("nonce")
            if algorithm != "MD5" or realm is None or not nonce:
                continue
            if _DIGEST_UNSAFE_RE.search(realm) or _DIGEST_UNSAFE_RE.search(nonce):
                continue
            qop_options = [
                item.strip() for item in params.get("qop", "").split(",") if item
            ]
            if qop_options and "auth" not in qop_options:
                continue
            self._realm = realm
            self._nonce = nonce
            self._opaque = params.get("opaque")
            self._qop = "auth" if qop_options else None
            self._nonce_count = 0
            return True
        return False

    def header(self, method: str, uri: str) -> str | None:
        """Return the Authorization header value, or None before a challenge."""
        if self._realm is None or self._nonce is None:
            return None
        ha1 = hashlib.md5(
            f"{self._username}:{self._realm}:{self._password}".encode()
        ).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        value = (
            f'Digest username="{self._username}", realm="{self._realm}", '
            f'nonce="{self._nonce}", uri="{uri}"'
        )
        if self._qop:
            self._nonce_count += 1
            nonce_count = f"{self._nonce_count:08x}"
            cnonce = secrets.token_hex(8)
            response = hashlib.md5(
                f"{ha1}:{self._nonce}:{nonce_count}:{cnonce}:{self._qop}:{ha2}".encode()
            ).hexdigest()
            value += (
                f', response="{response}", qop={self._qop}, '
                f'nc={nonce_count}, cnonce="{cnonce}"'
            )
        else:
            response = hashlib.md5(f"{ha1}:{self._nonce}:{ha2}".encode()).hexdigest()
            value += f', response="{response}"'
        if self._opaque is not None:
            value += f', opaque="{self._opaque}"'
        return value


class RtspBackchannelClient:
    """One RTSP session that sends G.711 audio to the intercom speaker."""

    def __init__(
        self,
        host: str,
        port: int,
        url: str,
        username: str,
        password: str,
    ) -> None:
        """Create a client for a credential-free ``rtsp://`` stream URL."""
        if _DIGEST_UNSAFE_RE.search(username):
            raise BackchannelError(REASON_AUTH, "RTSP username is not valid")
        self._host = host
        self._port = port
        self._url = url
        self._auth = _DigestAuth(username, password)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._cseq = 0
        self._session: str | None = None
        self._session_timeout = DEFAULT_SESSION_TIMEOUT
        self._track: BackchannelTrack | None = None
        self._channel = 0
        self._playing = False
        self._drain_task: asyncio.Task[None] | None = None
        self._connection_lost = False
        self._closing = False

    @property
    def track(self) -> BackchannelTrack | None:
        """Return the negotiated track once DESCRIBE succeeded."""
        return self._track

    async def async_describe(self) -> BackchannelTrack:
        """Connect and return the backchannel track offered by the device."""
        response = await self._request(
            "DESCRIBE", self._url, {"Accept": "application/sdp"}
        )
        if response.status != 200:
            raise self._status_error("DESCRIBE", response)
        base_url = (
            response.header("content-base")
            or response.header("content-location")
            or self._url
        )
        track = parse_backchannel_track(
            response.body.decode("utf-8", errors="ignore"), base_url
        )
        if track is None:
            raise BackchannelError(
                REASON_UNSUPPORTED,
                "The device does not offer a PCMU/PCMA audio backchannel track",
            )
        self._track = track
        return track

    async def async_start(self) -> BackchannelTrack:
        """Run DESCRIBE, SETUP and PLAY; afterwards audio can be sent."""
        track = self._track or await self.async_describe()

        response = await self._request(
            "SETUP",
            track.control,
            {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"},
        )
        if response.status != 200:
            raise self._status_error("SETUP", response)
        session = response.header("session")
        if not session:
            raise BackchannelError(
                REASON_CONNECTION, "SETUP answer has no Session header"
            )
        session_id, _, session_params = session.partition(";")
        self._session = session_id.strip()
        timeout_match = re.search(r"timeout\s*=\s*(\d+)", session_params)
        if timeout_match and int(timeout_match.group(1)) > 0:
            self._session_timeout = float(timeout_match.group(1))
        channel_match = re.search(
            r"interleaved\s*=\s*(\d+)", response.header("transport") or ""
        )
        if channel_match:
            self._channel = int(channel_match.group(1)) & 0xFF

        response = await self._request("PLAY", self._url, {})
        if response.status != 200:
            raise self._status_error("PLAY", response)

        self._playing = True
        self._drain_task = asyncio.ensure_future(self._drain_incoming())
        return track

    async def async_send_stream(
        self, source: asyncio.StreamReader, initial: bytes = b""
    ) -> int:
        """Send raw G.711 audio from ``source`` in real time.

        ``source`` must deliver 8 kHz mono samples in the codec of the
        negotiated track; ``initial`` is audio already read from it. Frames
        are read one at a time, so a fast source is slowed down to real
        time instead of being buffered. Returns the number of audio frames
        sent (without the trailing silence).
        """
        track = self._track
        if not self._playing or track is None or self._writer is None:
            raise BackchannelError(REASON_CONNECTION, "RTSP session is not playing")

        loop = asyncio.get_running_loop()
        sequence = secrets.randbelow(1 << 16)
        timestamp = secrets.randbelow(1 << 32)
        ssrc = secrets.randbelow(1 << 32)
        started = loop.time()
        next_keepalive = started + self._session_timeout / 2
        frames = 0
        trailing = 0
        source_done = False
        pending = initial

        while True:
            if source_done:
                if trailing >= TRAILING_SILENCE_FRAMES:
                    break
                payload = track.silence
                trailing += 1
            else:
                try:
                    while len(pending) < FRAME_BYTES:
                        pending += await source.readexactly(
                            FRAME_BYTES - len(pending)
                        )
                    payload, pending = pending[:FRAME_BYTES], pending[FRAME_BYTES:]
                except asyncio.IncompleteReadError as err:
                    source_done = True
                    partial = pending + err.partial
                    if not partial:
                        continue
                    payload = partial + track.silence[len(partial):]
                frames += 1

            index = frames + trailing - 1
            delay = started + index * FRAME_SECONDS - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

            if self._connection_lost:
                raise BackchannelError(
                    REASON_CONNECTION, "The device closed the RTSP connection"
                )
            packet = struct.pack(
                "!BBHII",
                0x80,
                track.payload_type | (0x80 if index == 0 else 0),
                sequence,
                timestamp,
                ssrc,
            ) + payload
            try:
                self._writer.write(
                    b"$" + struct.pack("!BH", self._channel, len(packet)) + packet
                )
                await self._writer.drain()
            except OSError as err:
                raise BackchannelError(
                    REASON_CONNECTION, f"RTSP connection lost: {type(err).__name__}"
                ) from err
            sequence = (sequence + 1) & 0xFFFF
            timestamp = (timestamp + FRAME_BYTES) & 0xFFFFFFFF

            if loop.time() >= next_keepalive:
                next_keepalive = loop.time() + self._session_timeout / 2
                self._write_request("GET_PARAMETER", self._url, {})

        return frames

    async def async_close(self) -> None:
        """Tear the session down (best effort) and close the connection."""
        drain_task, self._drain_task = self._drain_task, None
        if drain_task is not None:
            drain_task.cancel()
            await asyncio.gather(drain_task, return_exceptions=True)
        self._playing = False
        writer = self._writer
        if writer is None or self._closing:
            return
        self._closing = True
        try:
            if self._session and not self._connection_lost:
                self._write_request("TEARDOWN", self._url, {})
                await asyncio.wait_for(writer.drain(), timeout=1.0)
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug("RTSP TEARDOWN not sent: %s", type(err).__name__)
        finally:
            self._session = None
            self._writer = None
            self._reader = None
            self._closing = False
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            except (OSError, asyncio.TimeoutError):
                pass

    async def _connect(self) -> None:
        if self._writer is not None:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=RTSP_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise BackchannelError(
                REASON_CONNECTION,
                f"Cannot connect to the RTSP server: {type(err).__name__}",
            ) from err

    def _write_request(self, method: str, uri: str, headers: dict[str, str]) -> None:
        assert self._writer is not None
        self._cseq += 1
        lines = [
            f"{method} {uri} RTSP/1.0",
            f"CSeq: {self._cseq}",
            f"User-Agent: {USER_AGENT}",
            f"Require: {BACKCHANNEL_REQUIRE}",
        ]
        if self._session:
            lines.append(f"Session: {self._session}")
        authorization = self._auth.header(method, uri)
        if authorization:
            lines.append(f"Authorization: {authorization}")
        lines.extend(f"{name}: {value}" for name, value in headers.items())
        self._writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))

    async def _request(
        self, method: str, uri: str, headers: dict[str, str]
    ) -> _Response:
        """Send a request and return the answer, authenticating on 401."""
        await self._connect()
        response: _Response | None = None
        for attempt in range(2):
            try:
                self._write_request(method, uri, headers)
                assert self._writer is not None
                await self._writer.drain()
                response = await asyncio.wait_for(
                    self._read_response(), timeout=RTSP_TIMEOUT
                )
            except asyncio.TimeoutError as err:
                raise BackchannelError(
                    REASON_CONNECTION, f"No answer to RTSP {method}"
                ) from err
            except (OSError, asyncio.IncompleteReadError, ValueError) as err:
                raise BackchannelError(
                    REASON_CONNECTION,
                    f"RTSP {method} failed: {type(err).__name__}",
                ) from err
            if response.status != 401:
                return response
            if attempt == 1 or not self._auth.update(
                response.headers.get("www-authenticate", [])
            ):
                break
        raise BackchannelError(
            REASON_AUTH, "The RTSP server rejected the RTSP credentials"
        )

    async def _read_response(self) -> _Response:
        assert self._reader is not None
        reader = self._reader
        while True:
            first = await reader.readexactly(1)
            if first == b"$":
                # Interleaved RTP/RTCP from the device; not needed here.
                header = await reader.readexactly(3)
                await reader.readexactly(struct.unpack("!H", header[1:])[0])
                continue
            if first in b"\r\n":
                continue
            break
        head = first + await reader.readuntil(b"\r\n\r\n")
        if len(head) > _MAX_HEADER_BYTES:
            raise ValueError("RTSP header too long")
        lines = head.decode("utf-8", errors="ignore").split("\r\n")
        status_match = re.match(r"RTSP/\d\.\d\s+(\d{3})\s*(.*)", lines[0])
        if not status_match:
            raise ValueError("Not an RTSP answer")
        headers: dict[str, list[str]] = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if separator:
                headers.setdefault(name.strip().lower(), []).append(value.strip())
        length_values = headers.get("content-length", ["0"])
        length = int(length_values[0]) if length_values[0].isdigit() else 0
        if length > _MAX_BODY_BYTES:
            raise ValueError("RTSP body too long")
        body = await reader.readexactly(length) if length else b""
        return _Response(
            status=int(status_match.group(1)),
            reason=status_match.group(2).strip(),
            headers=headers,
            body=body,
        )

    async def _drain_incoming(self) -> None:
        """Discard everything the device sends while audio is streamed."""
        reader = self._reader
        if reader is None:
            return
        try:
            while await reader.read(4096):
                pass
        except OSError:
            pass
        self._connection_lost = True

    @staticmethod
    def _status_error(method: str, response: _Response) -> BackchannelError:
        # 551 Option not supported: the device does not know the backchannel
        # Require tag. 404/461: no such stream / transport for it.
        reason = (
            REASON_UNSUPPORTED
            if response.status in (404, 415, 461, 551)
            else REASON_CONNECTION
        )
        return BackchannelError(
            reason, f"RTSP {method} answered {response.status} {response.reason}"
        )
