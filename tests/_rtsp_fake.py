"""A tiny RTSP server with an ONVIF audio backchannel, for unit tests.

Listens on the loopback interface only. It checks Digest authentication,
answers DESCRIBE/SETUP/PLAY/GET_PARAMETER/TEARDOWN and records every request
and every interleaved RTP packet it receives.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import struct

REALM = "2N RTSP"
NONCE = "abcdef0123456789"

SDP_WITH_BACKCHANNEL = "\r\n".join(
    [
        "v=0",
        "o=- 1 1 IN IP4 0.0.0.0",
        "s=stream",
        "t=0 0",
        "a=control:*",
        "m=video 0 RTP/AVP 96",
        "a=rtpmap:96 H264/90000",
        "a=control:trackID=1",
        "a=recvonly",
        "m=audio 0 RTP/AVP 0",
        "a=control:trackID=2",
        "a=recvonly",
        "m=audio 0 RTP/AVP 0",
        "a=rtpmap:0 PCMU/8000",
        "a=control:trackID=3",
        "a=sendonly",
        "",
    ]
)

SDP_WITHOUT_BACKCHANNEL = "\r\n".join(
    [
        "v=0",
        "s=stream",
        "m=video 0 RTP/AVP 96",
        "a=rtpmap:96 H264/90000",
        "a=control:trackID=1",
        "a=recvonly",
        "",
    ]
)


class FakeRtspServer:
    """Scriptable RTSP server; use as ``async with FakeRtspServer() as srv``."""

    def __init__(
        self,
        *,
        username: str = "rtspuser",
        password: str = "s3cret-rtsp",
        sdp: str = SDP_WITH_BACKCHANNEL,
        qop: bool = True,
        describe_status: int = 200,
        close_after_packets: int | None = None,
        onvif_only: bool = False,
    ) -> None:
        # onvif_only mirrors firmware 3.x: the classic stream path answers
        # 551 to the backchannel Require header, the ONVIF media URL works.
        self.onvif_only = onvif_only
        self.username = username
        self.password = password
        self.sdp = sdp
        self.qop = qop
        self.describe_status = describe_status
        self.close_after_packets = close_after_packets
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.packets: list[tuple[int, bytes]] = []
        self.nonce_counts: list[str] = []
        self.torn_down = asyncio.Event()
        self.port = 0
        self._server: asyncio.AbstractServer | None = None

    async def __aenter__(self) -> "FakeRtspServer":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    @property
    def url(self) -> str:
        return f"rtsp://127.0.0.1:{self.port}/h264_stream"

    @property
    def onvif_url(self) -> str:
        return (
            f"rtsp://127.0.0.1:{self.port}"
            "/onvif/media?transport=unicast&profile=profile_h264_hq"
        )

    def methods(self) -> list[str]:
        return [method for method, _, _ in self.requests]

    def _authorized(self, method: str, headers: dict[str, str]) -> bool:
        value = headers.get("authorization", "")
        params = dict(re.findall(r'(\w+)="?([^",]+)"?', value))
        if not value.startswith("Digest") or params.get("username") != self.username:
            return False
        ha1 = hashlib.md5(
            f"{self.username}:{REALM}:{self.password}".encode()
        ).hexdigest()
        ha2 = hashlib.md5(f"{method}:{params.get('uri', '')}".encode()).hexdigest()
        if self.qop:
            self.nonce_counts.append(params.get("nc", ""))
            expected = hashlib.md5(
                f"{ha1}:{NONCE}:{params.get('nc')}:{params.get('cnonce')}:auth:{ha2}".encode()
            ).hexdigest()
        else:
            expected = hashlib.md5(f"{ha1}:{NONCE}:{ha2}".encode()).hexdigest()
        return params.get("response") == expected and params.get("nonce") == NONCE

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                first = await reader.readexactly(1)
                if first == b"$":
                    header = await reader.readexactly(3)
                    size = struct.unpack("!H", header[1:])[0]
                    self.packets.append((header[0], await reader.readexactly(size)))
                    if (
                        self.close_after_packets is not None
                        and len(self.packets) >= self.close_after_packets
                    ):
                        break
                    continue
                head = (first + await reader.readuntil(b"\r\n\r\n")).decode()
                lines = head.strip().split("\r\n")
                method, uri, _ = lines[0].split(" ", 2)
                headers = {
                    name.strip().lower(): value.strip()
                    for name, _, value in (line.partition(":") for line in lines[1:])
                }
                self.requests.append((method, uri, headers))
                if method == "TEARDOWN":
                    # The client does not wait for this answer.
                    self.torn_down.set()
                writer.write(self._answer(method, uri, headers).encode())
                await writer.drain()
                if method == "TEARDOWN":
                    break
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    def _answer(self, method: str, uri: str, headers: dict[str, str]) -> str:
        cseq = headers.get("cseq", "0")

        def reply(status: str, extra: list[str] | None = None, body: str = "") -> str:
            lines = [f"RTSP/1.0 {status}", f"CSeq: {cseq}", *(extra or [])]
            if body:
                lines.append(f"Content-Length: {len(body.encode())}")
            return "\r\n".join(lines) + "\r\n\r\n" + body

        if not self._authorized(method, headers):
            challenge = f'Digest realm="{REALM}", nonce="{NONCE}"'
            if self.qop:
                challenge += ', qop="auth"'
            return reply("401 Unauthorized", [f"WWW-Authenticate: {challenge}"])
        if method == "DESCRIBE":
            if self.describe_status != 200:
                return reply(f"{self.describe_status} Option not supported")
            if "/onvif/media" in uri:
                control = f"rtsp://127.0.0.1:{self.port}/onvif/media/audioback"
                return reply(
                    "200 OK",
                    ["Content-Type: application/sdp"],
                    self.sdp.replace("a=control:trackID=3", f"a=control:{control}"),
                )
            if self.onvif_only:
                return reply("551 Option not supported")
            return reply(
                "200 OK",
                ["Content-Type: application/sdp", f"Content-Base: {uri}/"],
                self.sdp,
            )
        if method == "SETUP":
            return reply(
                "200 OK",
                [
                    "Session: 12345678;timeout=60",
                    "Transport: RTP/AVP/TCP;unicast;interleaved=0-1",
                ],
            )
        return reply("200 OK", ["Session: 12345678"])
