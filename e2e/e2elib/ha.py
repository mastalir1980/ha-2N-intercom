"""Tiny Home Assistant client (REST + WebSocket) for the E2E tests and bootstrap."""

from __future__ import annotations

import itertools
import json
import time
from typing import Any

import requests
import websocket  # websocket-client

DOMAIN = "2n_intercom"


class HAError(RuntimeError):
    pass


class HA:
    def __init__(self, url: str, token: str | None = None, timeout: float = 15) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._ids = itertools.count(1)

    # ---------------------------------------------------------------- REST
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def get(self, path: str, **kw: Any) -> requests.Response:
        return requests.get(self.url + path, headers=self._headers(), timeout=self.timeout, **kw)

    def post(self, path: str, payload: Any = None, **kw: Any) -> requests.Response:
        return requests.post(
            self.url + path, headers=self._headers(), json=payload, timeout=self.timeout, **kw
        )

    def get_json(self, path: str) -> Any:
        r = self.get(path)
        if r.status_code != 200:
            raise HAError(f"GET {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def post_json(self, path: str, payload: Any = None) -> Any:
        r = self.post(path, payload)
        if r.status_code not in (200, 201):
            raise HAError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def is_up(self) -> bool:
        try:
            r = requests.get(self.url + "/manifest.json", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def wait_up(self, timeout: float = 300) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_up():
                return
            time.sleep(3)
        raise HAError(f"HA at {self.url} not up after {timeout:.0f}s")

    def state(self, entity_id: str) -> dict[str, Any]:
        return self.get_json(f"/api/states/{entity_id}")

    def call_service(self, domain: str, service: str, data: dict[str, Any] | None = None) -> Any:
        return self.post_json(f"/api/services/{domain}/{service}", data or {})

    def template(self, tpl: str) -> str:
        r = self.post("/api/template", {"template": tpl})
        if r.status_code != 200:
            raise HAError(f"template -> {r.status_code}: {r.text[:300]}")
        return r.text

    def config(self) -> dict[str, Any]:
        return self.get_json("/api/config")

    # ----------------------------------------------------------- WebSocket
    def ws(self, msg: dict[str, Any], timeout: float | None = None) -> Any:
        ws_url = self.url.replace("http", "ws", 1) + "/api/websocket"
        conn = websocket.create_connection(ws_url, timeout=timeout or self.timeout)
        try:
            json.loads(conn.recv())  # auth_required
            conn.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth = json.loads(conn.recv())
            if auth.get("type") != "auth_ok":
                raise HAError(f"websocket auth failed: {auth}")
            msg_id = next(self._ids)
            conn.send(json.dumps({**msg, "id": msg_id}))
            while True:
                reply = json.loads(conn.recv())
                if reply.get("id") == msg_id and reply.get("type") == "result":
                    if not reply.get("success"):
                        raise HAError(f"ws {msg.get('type')} failed: {reply.get('error')}")
                    return reply.get("result")
        finally:
            conn.close()

    def entries(self, domain: str = DOMAIN) -> list[dict[str, Any]]:
        return self.ws({"type": "config_entries/get", "domain": domain})

    def entity_registry(self, platform: str = DOMAIN) -> list[dict[str, Any]]:
        return [e for e in self.ws({"type": "config/entity_registry/list"}) if e.get("platform") == platform]

    def devices(self, entry_id: str) -> list[dict[str, Any]]:
        return [
            d for d in self.ws({"type": "config/device_registry/list"})
            if entry_id in (d.get("config_entries") or [])
        ]

    def system_log(self) -> list[dict[str, Any]]:
        return self.ws({"type": "system_log/list"})

    def reload_entry(self, entry_id: str) -> Any:
        return self.post_json(f"/api/config/config_entries/entry/{entry_id}/reload")

    # ------------------------------------------------------- options flows
    def options_flow_start(self, entry_id: str) -> dict[str, Any]:
        return self.post_json("/api/config/config_entries/options/flow", {"handler": entry_id})

    def options_flow_submit(self, flow_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self.post_json(f"/api/config/config_entries/options/flow/{flow_id}", data)

    def options_flow_abort(self, flow_id: str) -> None:
        r = requests.delete(
            f"{self.url}/api/config/config_entries/options/flow/{flow_id}",
            headers=self._headers(), timeout=self.timeout,
        )
        if r.status_code not in (200, 204, 404):
            raise HAError(f"DELETE options flow {flow_id} -> {r.status_code}: {r.text[:300]}")

    # -------------------------------------------------------------- helpers
    def wait_for(self, predicate, timeout: float, interval: float = 0.5, what: str = "condition") -> Any:
        deadline = time.monotonic() + timeout
        last: Any = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(interval)
        raise AssertionError(f"timeout after {timeout}s waiting for {what} (last={last!r})")
