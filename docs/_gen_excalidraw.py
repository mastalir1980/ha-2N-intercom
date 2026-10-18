"""Generator for the Excalidraw diagrams shipped under docs/.

Run with: python3 docs/_gen_excalidraw.py
Produces deterministic .excalidraw JSON (no random seeds / timestamps) so the
files diff cleanly. Kept in-repo so the diagrams can be regenerated/edited.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent

# Palette
BLUE = {"bg": "#a5d8ff", "stroke": "#1971c2"}
GREEN = {"bg": "#b2f2bb", "stroke": "#2f9e44"}
ORANGE = {"bg": "#ffd8a8", "stroke": "#e8590c"}
GRAY = {"bg": "#e9ecef", "stroke": "#495057"}
VIOLET = {"bg": "#d0bfff", "stroke": "#6741d9"}
RED = {"bg": "#ffc9c9", "stroke": "#e03131"}


def _base(idx: int) -> dict:
    return {
        "id": f"el{idx}",
        "seed": 1000 + idx,
        "version": 1,
        "versionNonce": 1000 + idx,
        "isDeleted": False,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
    }


class Builder:
    def __init__(self) -> None:
        self.els: list[dict] = []
        self.i = 0

    def _next(self) -> int:
        self.i += 1
        return self.i

    def box(self, x, y, w, h, text, color=GRAY, font=16, dashed=False):
        idx = self._next()
        rect = _base(idx)
        rect.update(
            {
                "type": "rectangle",
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "backgroundColor": color["bg"],
                "strokeColor": color["stroke"],
                "fillStyle": "solid",
                "roundness": {"type": 3},
                "strokeStyle": "dashed" if dashed else "solid",
            }
        )
        self.els.append(rect)
        tidx = self._next()
        t = _base(tidx)
        lines = text.split("\n")
        t.update(
            {
                "type": "text",
                "x": x + 8,
                "y": y + h / 2 - (font * 1.25 * len(lines)) / 2,
                "width": w - 16,
                "height": font * 1.25 * len(lines),
                "text": text,
                "rawText": text,
                "fontSize": font,
                "fontFamily": 2,
                "textAlign": "center",
                "verticalAlign": "middle",
                "strokeColor": color["stroke"],
                "containerId": None,
                "originalText": text,
                "lineHeight": 1.25,
                "baseline": font,
            }
        )
        self.els.append(t)
        return rect

    def label(self, x, y, text, font=14, color="#495057"):
        idx = self._next()
        lines = text.split("\n")
        t = _base(idx)
        t.update(
            {
                "type": "text",
                "x": x,
                "y": y,
                "width": max(len(l) for l in lines) * font * 0.6,
                "height": font * 1.25 * len(lines),
                "text": text,
                "rawText": text,
                "fontSize": font,
                "fontFamily": 2,
                "textAlign": "left",
                "verticalAlign": "top",
                "strokeColor": color,
                "containerId": None,
                "originalText": text,
                "lineHeight": 1.25,
                "baseline": font,
            }
        )
        self.els.append(t)
        return t

    def arrow(self, x1, y1, x2, y2, color="#495057", dashed=False, label=None):
        idx = self._next()
        a = _base(idx)
        a.update(
            {
                "type": "arrow",
                "x": x1,
                "y": y1,
                "width": abs(x2 - x1),
                "height": abs(y2 - y1),
                "points": [[0, 0], [x2 - x1, y2 - y1]],
                "strokeColor": color,
                "strokeStyle": "dashed" if dashed else "solid",
                "startBinding": None,
                "endBinding": None,
                "startArrowhead": None,
                "endArrowhead": "arrow",
                "lastCommittedPoint": None,
            }
        )
        self.els.append(a)
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.label(mx - len(label) * 3, my - 18, label, font=12, color=color)
        return a

    def dump(self, name: str) -> None:
        doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://github.com/savek-cc/ha-2N-intercom",
            "elements": self.els,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }
        (OUT_DIR / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Diagram 1 — Component architecture
# ---------------------------------------------------------------------------
b = Builder()
b.label(360, 10, "2N Intercom — Component Architecture", font=22, color="#1e1e1e")

# HA core
b.box(360, 70, 320, 50, "Home Assistant Core", BLUE, font=18)

# Config / setup column
b.box(40, 70, 240, 50, "config_flow.py\n(Config + Options Flow)", VIOLET)
b.box(40, 160, 240, 60, "__init__.py\nasync_setup_entry / services\nanswer_call · hangup_call", VIOLET)

# Coordinator
b.box(360, 170, 320, 80,
      "coordinator.py\nTwoNIntercomCoordinator\n(DataUpdateCoordinator + cache)", GREEN, font=16)

# Log listener
b.box(360, 300, 320, 60,
      "Log-listener background task\nsubscribe → pull → apply events", GREEN)

# API client
b.box(360, 410, 320, 70,
      "api.py — TwoNIntercomAPI\nHTTP (Digest→Basic) + RTSP probe", ORANGE, font=16)

# Device
b.box(360, 540, 320, 70,
      "2N IP Intercom device\n/api/* HTTP API  +  RTSP server", RED, font=16)

# Platforms (entities)
plat_y = 170
b.box(760, plat_y, 200, 40, "camera.py (MjpegCamera)", BLUE, font=13)
b.box(760, plat_y + 55, 200, 40, "binary_sensor.py\n(input · relay-active · motion)", BLUE, font=12)
b.box(760, plat_y + 110, 200, 40, "switch.py (door relays)", BLUE, font=13)
b.box(760, plat_y + 165, 200, 40, "cover.py (gate relays)", BLUE, font=13)
b.box(760, plat_y + 220, 200, 40, "sensor.py (SIP · call state)", BLUE, font=13)
b.box(760, plat_y + 275, 200, 40, "diagnostics.py", GRAY, font=13)
b.box(760, plat_y + 330, 200, 40, "entity.py (shared base)", GRAY, font=13)
b.box(760, plat_y + 385, 200, 40, "event.py (doorbell rings)", BLUE, font=13)

# Arrows
b.arrow(280, 185, 360, 200, color="#6741d9", label="setup")
b.arrow(520, 120, 520, 170, color="#1971c2", label="register")
b.arrow(520, 250, 520, 300, color="#2f9e44")
b.arrow(520, 360, 520, 410, color="#2f9e44", label="poll/subscribe")
b.arrow(520, 480, 520, 540, color="#e8590c", label="HTTPS / RTSP")
b.arrow(680, 210, 760, 200, color="#2f9e44", label="runtime_data\n+ listeners")
b.arrow(160, 120, 160, 160, color="#6741d9")

b.dump("architecture.excalidraw")

# ---------------------------------------------------------------------------
# Diagram 2 — Event / data flow (ring + state updates)
# ---------------------------------------------------------------------------
b = Builder()
b.label(300, 10, "Event-driven data flow (local_push)", font=22, color="#1e1e1e")

lane_x = [40, 320, 640, 960]
b.box(lane_x[0], 60, 220, 40, "2N Device", RED, font=15)
b.box(lane_x[1], 60, 220, 40, "API client", ORANGE, font=15)
b.box(lane_x[2], 60, 220, 40, "Coordinator", GREEN, font=15)
b.box(lane_x[3], 60, 220, 40, "HA Entities", BLUE, font=15)

steps = [
    "/api/log/subscribe (events filter)",
    "subscription id",
    "loop: /api/log/pull (timeout=1s)",
    "events: CallStateChanged,\nSwitchStateChanged, InputChanged,\nMotionDetected, ConfigurationChanged…",
    "_process_log_event() patches\ncached status in place",
    "async_update_listeners()",
    "is_on / native_value / ring event\nread from cache → UI update",
]
y = 130
for i, s in enumerate(steps):
    color = GRAY
    b.box(300, y, 520, 56, s, color, font=13)
    y += 76

# side arrows showing direction
b.arrow(150, 120, 150, 720, color="#e03131", dashed=True)
b.arrow(430, 120, 430, 720, color="#e8590c", dashed=True)
b.arrow(750, 120, 750, 720, color="#2f9e44", dashed=True)
b.arrow(1070, 120, 1070, 720, color="#1971c2", dashed=True)

b.label(40, 760,
        "Polling every scan_interval (default 60s) is only a safety net:\n"
        "/api/phone/status, /api/switch/status, /api/io/status, /api/call/status\n"
        "re-establish baseline if a pushed event is ever missed.",
        font=13)

b.dump("event-flow.excalidraw")

print("wrote architecture.excalidraw and event-flow.excalidraw")
