"""Minimal direct 2N HTTP API client — the 'ground truth' side of the E2E tests.

Independent of the integration's api.py on purpose: if both shared code, a bug
in api.py would be invisible to the tests.
"""

from __future__ import annotations

from typing import Any

import requests
import urllib3
from requests.auth import HTTPBasicAuth, HTTPDigestAuth


class TwoN:
    def __init__(self, host: str, user: str, password: str, protocol: str = "https", verify: bool = False) -> None:
        self.base = f"{protocol}://{host}"
        self.user, self.password = user, password
        self.verify = verify
        self._auth: Any = HTTPDigestAuth(user, password)
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _auth_for(self, challenge: str) -> Any:
        if challenge.lower().startswith("basic"):
            return HTTPBasicAuth(self.user, self.password)
        return HTTPDigestAuth(self.user, self.password)

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET with per-request auth: 2N configures Basic/Digest per service group,
        so the scheme is picked from each 401 challenge, never fixed globally."""
        kw = dict(params=params or None, verify=self.verify, timeout=10)
        r = requests.get(self.base + path, auth=self._auth, **kw)
        if r.status_code == 401:
            challenge = r.headers.get("WWW-Authenticate", "")
            r = requests.get(self.base + path, auth=self._auth_for(challenge), **kw)
        if r.status_code == 401:
            raise PermissionError(
                f"2N {path}: 401 — the API user lacks the privilege for this service "
                f"or uses the wrong auth scheme (challenge: {r.headers.get('WWW-Authenticate', '?')[:40]})"
            )
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise RuntimeError(f"2N {path} failed: {body.get('error')}")
        return body.get("result", {})

    def system_info(self) -> dict[str, Any]:
        return self._get("/api/system/info")

    def system_caps(self) -> dict[str, Any]:
        return self._get("/api/system/caps")

    def switch_caps(self) -> list[dict[str, Any]]:
        return self._get("/api/switch/caps").get("switches", [])

    def switch_status(self) -> list[dict[str, Any]]:
        return self._get("/api/switch/status").get("switches", [])

    def io_caps(self) -> list[dict[str, Any]]:
        return self._get("/api/io/caps").get("ports", [])

    def io_status(self) -> list[dict[str, Any]]:
        return self._get("/api/io/status").get("ports", [])

    def phone_status(self) -> list[dict[str, Any]]:
        return self._get("/api/phone/status").get("accounts", [])

    def dir_users(self) -> list[dict[str, Any]]:
        """Read directory UUIDs and names independently of the integration."""
        path = "/api/dir/query"
        kw = dict(
            # UUID accompanies each entry independently of the selected fields.
            json={"iterator": {"timestamp": 0}, "fields": ["name"]},
            verify=self.verify,
            timeout=10,
        )
        r = requests.post(self.base + path, auth=self._auth, **kw)
        if r.status_code == 401:
            challenge = r.headers.get("WWW-Authenticate", "")
            r = requests.post(self.base + path, auth=self._auth_for(challenge), **kw)
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            error = body.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            detail = f" (code {code})" if type(code) is int else ""
            raise RuntimeError(f"2N /api/dir/query failed{detail}")
        return body["result"]["users"]

    def relay_active(self, number: int) -> bool:
        for sw in self.switch_status():
            if sw.get("switch") == number:
                return bool(sw.get("active"))
        raise KeyError(f"relay {number} not reported by device")

    # ------------------------------------------------------------ log channel
    def log_caps(self) -> list[str]:
        return list(self._get("/api/log/caps").get("events", []))

    def log_subscribe(self, events: list[str]) -> int:
        return int(self._get("/api/log/subscribe", filter=",".join(events))["id"])

    def log_pull(self, sub_id: int, timeout: int = 0) -> list[dict[str, Any]]:
        return list(self._get("/api/log/pull", id=sub_id, timeout=timeout).get("events", []))

    def log_unsubscribe(self, sub_id: int) -> None:
        self._get("/api/log/unsubscribe", id=sub_id)
