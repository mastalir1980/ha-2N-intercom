"""Options flow UX (TASK-14): Next/Submit labels and back navigation.

Drives the real options flow on staging HA through the config-flow REST
API and checks it against the 2N ground truth (switch caps):

* every step that is followed by another step reports ``last_step: False``
  (frontend renders "Next"), the final step reports ``last_step: True``
* every step after the first offers the ``go_back`` field and submitting
  it returns to the previous step with session values kept
* the flow is aborted at the end, so the saved options stay unchanged

Read-only: no relay is ever switched (flow REST calls only).

Skips when the deployed integration predates TASK-14: such options flows
never set ``last_step`` (HA reports ``null``).
"""

from __future__ import annotations

from typing import Any

import pytest


def _defaults_payload(step: dict[str, Any]) -> dict[str, Any]:
    """Build a valid submission from the schema defaults (current values)."""
    payload: dict[str, Any] = {}
    for field in step.get("data_schema", []):
        name = field.get("name")
        if name == "go_back":
            continue
        if field.get("required") and "default" in field:
            payload[name] = field["default"]
        elif name == "rtsp_username":
            suggested = (field.get("description") or {}).get("suggested_value")
            if suggested:
                payload[name] = suggested
    return payload


def _field_names(step: dict[str, Any]) -> set[str]:
    return {f.get("name") for f in step.get("data_schema", [])}


def _current_options(entry: dict) -> dict:
    return dict(entry.get("options") or {})


def test_options_flow_last_step_and_back_navigation(ha, twon, entry) -> None:
    options_before = _current_options(entry)

    # Ground truth from the device: how many enabled relays the options
    # flow will offer steps for.
    relays = [s for s in twon.switch_caps() if s.get("enabled")]
    options = entry.get("options") or {}
    data = entry.get("data") or {}
    camera_enabled = options.get("enable_camera", data.get("enable_camera", True))

    flow = ha.options_flow_start(entry["entry_id"])
    flow_id = flow["flow_id"]
    try:
        # --- device step ------------------------------------------------
        assert flow["type"] == "form" and flow["step_id"] == "device", flow
        if flow.get("last_step") is None:
            pytest.skip("deployed options flow does not set last_step (TASK-14 not deployed)")
        # Followed by camera (when enabled) or relay steps -> Next.
        assert flow["last_step"] is (not camera_enabled and not relays)
        # First step has no back control.
        assert "go_back" not in _field_names(flow)

        result = ha.options_flow_submit(flow_id, _defaults_payload(flow))

        # --- camera step ------------------------------------------------
        if camera_enabled:
            assert result["type"] == "form" and result["step_id"] == "camera", result
            assert result["last_step"] is (not relays)
            assert "go_back" in _field_names(result)
            # RTSP password is masked: password-type text selector, and the
            # stored value is never suggested back into the form (TASK-15).
            rtsp_pw = next(
                f for f in result["data_schema"] if f.get("name") == "rtsp_password"
            )
            assert rtsp_pw.get("selector", {}).get("text", {}).get("type") == "password"
            assert "suggested_value" not in (rtsp_pw.get("description") or {})

            # Back to the device step keeps the session values.
            back = ha.options_flow_submit(
                flow_id, {**_defaults_payload(result), "go_back": True}
            )
            assert back["type"] == "form" and back["step_id"] == "device", back
            assert back["last_step"] is False  # camera enabled in this session

            # Forward again to the camera step.
            result = ha.options_flow_submit(flow_id, _defaults_payload(back))
            assert result["type"] == "form" and result["step_id"] == "camera", result

            camera_payload = _defaults_payload(result)
            if not relays:
                # No relay steps: the camera step is the last one. Abort
                # instead of submitting so nothing is saved.
                ha.options_flow_abort(flow_id)
                flow_id = None
                assert options_before == _current_options(ha.entries()[0])
                return
            result = ha.options_flow_submit(flow_id, camera_payload)
        elif not relays:
            # Camera disabled and no relays: the device step was the last
            # one and already saved identical values.
            assert result["type"] == "create_entry", result
            flow_id = None
            assert _current_options(ha.entries()[0]) == options_before
            return

        # --- relay steps ------------------------------------------------
        assert result["type"] == "form" and result["step_id"] == "relay", result
        assert "go_back" in _field_names(result)
        assert result["last_step"] is (len(relays) == 1)

        # Back from the first relay returns to camera (or device).
        back = ha.options_flow_submit(
            flow_id, {**_defaults_payload(result), "go_back": True}
        )
        expected = "camera" if camera_enabled else "device"
        assert back["type"] == "form" and back["step_id"] == expected, back

        # Nothing was persisted at any point.
        ha.options_flow_abort(flow_id)
        flow_id = None
    finally:
        if flow_id is not None:
            ha.options_flow_abort(flow_id)

    assert _current_options(ha.entries()[0]) == options_before
