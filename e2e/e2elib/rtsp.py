"""Minimal RTSP DESCRIBE client for the E2E suite (ground truth for the speaker).

Deliberately independent of the integration's ``backchannel.py``: it only asks
the intercom whether its SDP offers an ONVIF audio backchannel track. Read-only:
it never opens a session and never sends audio.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import socket

REQUIRE = "www.onvif.org/ver20/backchannel"
# Where a 2N intercom may offer the backchannel: the ONVIF media URL (fw 3.x)
# and the classic stream path.
PATHS = ("onvif/media?transport=unicast&profile=profile_h264_hq", "h264_stream")


def _read_answer(sock: socket.socket) -> tuple[int, str, str]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("RTSP server closed the connection")
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    text = head.decode("utf-8", errors="ignore")
    length = int((re.search(r"(?im)^content-length:\s*(\d+)", text) or [0, 0])[1])
    while len(body) < length:
        chunk = sock.recv(4096)
        if not chunk:
            break
        body += chunk
    return int(text.split()[1]), text, body.decode("utf-8", errors="ignore")


def _digest(challenge: str, user: str, password: str, method: str, uri: str) -> str:
    realm = re.search(r'realm="([^"]*)"', challenge)[1]
    nonce = re.search(r'nonce="([^"]*)"', challenge)[1]
    ha1 = hashlib.md5(f"{user}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    value = f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}"'
    if re.search(r'qop="?[^",]*auth', challenge):
        cnonce = secrets.token_hex(8)
        response = hashlib.md5(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}".encode()).hexdigest()
        return f'{value}, response="{response}", qop=auth, nc=00000001, cnonce="{cnonce}"'
    response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return f'{value}, response="{response}"'


def describe(host: str, user: str, password: str, *, port: int = 554,
             path: str = "h264_stream", timeout: float = 5) -> tuple[int, str]:
    """Return (status, SDP) of a DESCRIBE that asks for the audio backchannel."""
    uri = f"rtsp://{host}:{port}/{path}"
    with socket.create_connection((host, port), timeout=timeout) as sock:
        authorization = ""
        for cseq in (1, 2):
            sock.sendall((
                f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: {cseq}\r\nUser-Agent: ha2n-e2e\r\n"
                f"Accept: application/sdp\r\nRequire: {REQUIRE}\r\n{authorization}\r\n"
            ).encode())
            status, head, body = _read_answer(sock)
            if status != 401 or cseq == 2:
                return status, body
            challenge = re.search(r"(?im)^www-authenticate:\s*(Digest .*)$", head)
            if not challenge:
                return status, body
            authorization = (
                f"Authorization: {_digest(challenge[1], user, password, 'DESCRIBE', uri)}\r\n"
            )
    raise AssertionError("unreachable")


def backchannel_codecs(sdp: str) -> list[str]:
    """Return the G.711 codecs of the ``sendonly`` audio sections of an SDP."""
    codecs: list[str] = []
    for section in re.split(r"(?m)^(?=m=)", sdp)[1:]:
        lines = [line.strip() for line in section.splitlines()]
        media = lines[0][2:].split()
        if media[0] != "audio" or "a=sendonly" not in lines:
            continue
        names = {"0": "PCMU", "8": "PCMA"}
        for line in lines:
            m = re.match(r"a=rtpmap:(\d+)\s+([^/\s]+)/(\d+)", line)
            if m:
                names[m[1]] = m[2].upper() if m[3] == "8000" else f"{m[2].upper()}/{m[3]}"
        codecs += [names[pt] for pt in media[3:] if names.get(pt) in ("PCMU", "PCMA")]
    return codecs
