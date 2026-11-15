"""Unit tests for the RTSP audio backchannel client (fake loopback server)."""

from __future__ import annotations

import asyncio
import struct
import unittest

from _rtsp_fake import SDP_WITHOUT_BACKCHANNEL, FakeRtspServer
from _stubs import INTEGRATION_DIR, ensure_package, load_module

BACKCHANNEL_PATH = INTEGRATION_DIR / "backchannel.py"
LOGGER_NAME = "custom_components.2n_intercom.backchannel"


def load_backchannel_module():
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    return load_module(LOGGER_NAME, BACKCHANNEL_PATH)


def _reader(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class SdpParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_backchannel_module()

    def _parse(self, *media_lines: str, base: str = "rtsp://host:554/h264_stream/"):
        sdp = "\r\n".join(["v=0", "s=x", "a=control:*", *media_lines, ""])
        return self.module.parse_backchannel_track(sdp, base)

    def test_picks_the_sendonly_audio_track_and_resolves_its_control(self) -> None:
        track = self._parse(
            "m=video 0 RTP/AVP 96", "a=control:trackID=1", "a=recvonly",
            "m=audio 0 RTP/AVP 0", "a=control:trackID=2", "a=recvonly",
            "m=audio 0 RTP/AVP 0", "a=control:trackID=3", "a=sendonly",
        )
        self.assertEqual(track.control, "rtsp://host:554/h264_stream/trackID=3")
        self.assertEqual((track.payload_type, track.codec), (0, "PCMU"))
        self.assertEqual(track.ffmpeg_format, "mulaw")
        self.assertEqual(track.silence, b"\xff" * 160)

    def test_absolute_control_and_dynamic_pcma_payload_type(self) -> None:
        track = self._parse(
            "m=audio 0 RTP/AVP 97 98",
            "a=rtpmap:97 G726-32/8000",
            "a=rtpmap:98 pcma/8000",
            "a=control:rtsp://other:554/back",
            "a=sendonly",
        )
        self.assertEqual(track.control, "rtsp://other:554/back")
        self.assertEqual((track.payload_type, track.codec), (98, "PCMA"))
        self.assertEqual(track.ffmpeg_format, "alaw")
        self.assertEqual(track.silence, b"\xd5" * 160)

    def test_no_track_without_sendonly_audio_or_supported_codec(self) -> None:
        self.assertIsNone(
            self._parse("m=audio 0 RTP/AVP 0", "a=control:trackID=2", "a=recvonly")
        )
        self.assertIsNone(
            self._parse("m=video 0 RTP/AVP 96", "a=control:t", "a=sendonly")
        )
        self.assertIsNone(
            self._parse(
                "m=audio 0 RTP/AVP 96", "a=rtpmap:96 MPEG4-GENERIC/16000",
                "a=control:t", "a=sendonly",
            )
        )
        # PCMU at another clock rate is not what the client sends.
        self.assertIsNone(
            self._parse(
                "m=audio 0 RTP/AVP 96", "a=rtpmap:96 PCMU/16000",
                "a=control:t", "a=sendonly",
            )
        )


class BackchannelClientTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_backchannel_module()

    def setUp(self) -> None:
        self._frame_seconds = self.module.FRAME_SECONDS
        self.module.FRAME_SECONDS = 0.0005
        self.addCleanup(setattr, self.module, "FRAME_SECONDS", self._frame_seconds)

    def _client(self, server: FakeRtspServer, password: str | None = None):
        return self.module.RtspBackchannelClient(
            "127.0.0.1",
            server.port,
            server.url,
            server.username,
            server.password if password is None else password,
        )

    async def test_full_session_sends_paced_rtp_and_tears_down(self) -> None:
        audio = bytes(range(256)) * 2  # 512 bytes = 3 full frames + 32 bytes
        async with FakeRtspServer() as server:
            client = self._client(server)
            track = await client.async_start()
            frames = await client.async_send_stream(_reader(audio[160:]), audio[:160])
            await client.async_close()
            await asyncio.wait_for(server.torn_down.wait(), timeout=2)

        self.assertEqual(track.codec, "PCMU")
        self.assertEqual(frames, 4)
        self.assertEqual(
            server.methods(),
            ["DESCRIBE", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN"],
        )
        for method, uri, headers in server.requests:
            self.assertEqual(headers["require"], "www.onvif.org/ver20/backchannel")
            self.assertNotIn(server.password, uri)
            self.assertNotIn(server.password, " ".join(headers.values()))
        setup = server.requests[2]
        self.assertEqual(setup[1], f"{server.url}/trackID=3")
        self.assertEqual(
            setup[2]["transport"], "RTP/AVP/TCP;unicast;interleaved=0-1"
        )
        for _, _, headers in server.requests[3:]:
            self.assertEqual(headers["session"], "12345678")
        # One Digest challenge, then an increasing nonce count.
        self.assertEqual(
            server.nonce_counts, ["00000001", "00000002", "00000003", "00000004"]
        )

        trailing = self.module.TRAILING_SILENCE_FRAMES
        self.assertEqual(len(server.packets), 4 + trailing)
        payload = b""
        previous = None
        for index, (channel, packet) in enumerate(server.packets):
            first, second, sequence, timestamp, ssrc = struct.unpack(
                "!BBHII", packet[:12]
            )
            self.assertEqual(channel, 0)
            self.assertEqual(first, 0x80)
            self.assertEqual(second & 0x7F, 0)
            self.assertEqual(bool(second & 0x80), index == 0)
            self.assertEqual(len(packet), 12 + 160)
            if previous is not None:
                self.assertEqual(sequence, (previous[0] + 1) & 0xFFFF)
                self.assertEqual(timestamp, (previous[1] + 160) & 0xFFFFFFFF)
                self.assertEqual(ssrc, previous[2])
            previous = (sequence, timestamp, ssrc)
            payload += packet[12:]
        self.assertEqual(payload[:512], audio)
        # The last partial frame and the tail are padded with mu-law silence.
        self.assertEqual(payload[512:], b"\xff" * (len(payload) - 512))

    async def test_digest_without_qop(self) -> None:
        async with FakeRtspServer(qop=False) as server:
            client = self._client(server)
            track = await client.async_describe()
            await client.async_close()
        self.assertEqual(track.payload_type, 0)
        self.assertEqual(server.methods(), ["DESCRIBE", "DESCRIBE"])

    async def test_wrong_password_is_an_auth_error_without_the_password(self) -> None:
        async with FakeRtspServer() as server:
            client = self._client(server, password="wrong-pass-123")
            with self.assertLogs(LOGGER_NAME, level="DEBUG") as logs:
                self.module._LOGGER.debug("marker")
                with self.assertRaises(self.module.BackchannelError) as raised:
                    await client.async_start()
                await client.async_close()
        self.assertEqual(raised.exception.reason, self.module.REASON_AUTH)
        self.assertNotIn("wrong-pass-123", str(raised.exception))
        self.assertNotIn("wrong-pass-123", "\n".join(logs.output))
        # Unauthenticated try plus exactly one authenticated retry.
        self.assertEqual(server.methods(), ["DESCRIBE", "DESCRIBE"])

    async def test_missing_track_and_unknown_require_are_unsupported(self) -> None:
        for kwargs in ({"sdp": SDP_WITHOUT_BACKCHANNEL}, {"describe_status": 551}):
            with self.subTest(**kwargs):
                async with FakeRtspServer(**kwargs) as server:
                    client = self._client(server)
                    with self.assertRaises(self.module.BackchannelError) as raised:
                        await client.async_describe()
                    await client.async_close()
                self.assertEqual(
                    raised.exception.reason, self.module.REASON_UNSUPPORTED
                )
                self.assertNotIn("SETUP", server.methods())

    async def test_unreachable_server_is_a_connection_error(self) -> None:
        async with FakeRtspServer() as server:
            port = server.port
        client = self.module.RtspBackchannelClient(
            "127.0.0.1", port, f"rtsp://127.0.0.1:{port}/h264_stream", "u", "p"
        )
        with self.assertRaises(self.module.BackchannelError) as raised:
            await client.async_describe()
        self.assertEqual(raised.exception.reason, self.module.REASON_CONNECTION)
        await client.async_close()

    async def test_device_closing_the_connection_stops_the_stream(self) -> None:
        self.module.FRAME_SECONDS = 0.005
        async with FakeRtspServer(close_after_packets=3) as server:
            client = self._client(server)
            await client.async_start()
            with self.assertRaises(self.module.BackchannelError) as raised:
                await client.async_send_stream(_reader(b"\x00" * 160 * 400))
            await client.async_close()
        self.assertEqual(raised.exception.reason, self.module.REASON_CONNECTION)
        self.assertNotIn("TEARDOWN", server.methods())

    async def test_keepalive_is_sent_while_streaming(self) -> None:
        async with FakeRtspServer() as server:
            client = self._client(server)
            await client.async_start()
            client._session_timeout = 0.0
            await client.async_send_stream(_reader(b"\x00" * 320))
            await client.async_close()
            await asyncio.wait_for(server.torn_down.wait(), timeout=2)
        keepalives = [r for r in server.requests if r[0] == "GET_PARAMETER"]
        self.assertTrue(keepalives)
        self.assertEqual(keepalives[0][2]["session"], "12345678")

    async def test_e2e_ground_truth_client_reads_the_same_server(self) -> None:
        """The independent E2E DESCRIBE helper agrees with the fake device."""
        import sys

        sys.path.insert(0, str(INTEGRATION_DIR.parents[1] / "e2e"))
        from e2elib import rtsp

        for sdp, expected in ((None, ["PCMU"]), (SDP_WITHOUT_BACKCHANNEL, [])):
            kwargs = {} if sdp is None else {"sdp": sdp}
            for qop in (True, False):
                with self.subTest(expected=expected, qop=qop):
                    async with FakeRtspServer(qop=qop, **kwargs) as server:
                        status, body = await asyncio.to_thread(
                            rtsp.describe,
                            "127.0.0.1",
                            server.username,
                            server.password,
                            port=server.port,
                        )
                        self.assertEqual(status, 200)
                        self.assertEqual(rtsp.backchannel_codecs(body), expected)
                        self.assertEqual(server.methods(), ["DESCRIBE", "DESCRIBE"])
                        wrong = await asyncio.to_thread(
                            rtsp.describe, "127.0.0.1", server.username, "nope",
                            port=server.port,
                        )
                        self.assertEqual(wrong[0], 401)

    async def test_invalid_username_is_rejected_before_connecting(self) -> None:
        with self.assertRaises(self.module.BackchannelError) as raised:
            self.module.RtspBackchannelClient(
                "127.0.0.1", 1, "rtsp://127.0.0.1:1/h264_stream", 'a"b', "p"
            )
        self.assertEqual(raised.exception.reason, self.module.REASON_AUTH)

    async def test_send_requires_a_playing_session(self) -> None:
        client = self.module.RtspBackchannelClient(
            "127.0.0.1", 1, "rtsp://127.0.0.1:1/h264_stream", "u", "p"
        )
        with self.assertRaises(self.module.BackchannelError):
            await client.async_send_stream(_reader(b""))


if __name__ == "__main__":
    unittest.main()
