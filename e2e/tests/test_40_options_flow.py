"""Options flow UX: Next/Submit labels and forward-only navigation.

Drives the real options flow on staging HA through the config-flow REST
API and checks it against the 2N ground truth (switch caps):

* every step that is followed by another step reports ``last_step: False``
  (frontend renders "Next"), the final step reports ``last_step: True``
* no step offers the ``go_back`` field; submissions only move forward
* saved options stay unchanged at each intermediate step and after aborting
  the final form without submitting it
* grant-access user options show the names returned by the device directory
* event picture saving requires retention, without saving the options draft

Read-only: no relay is ever switched (flow REST calls only).
"""

from __future__ import annotations

from typing import Any

import pytest


def _defaults_payload(step: dict[str, Any]) -> dict[str, Any]:
    """Build a valid submission from the schema defaults (current values)."""
    payload: dict[str, Any] = {}
    for field in step.get("data_schema", []):
        name = field.get("name")
        if field.get("required") and "default" in field:
            payload[name] = field["default"]
        elif name in ("rtsp_username", "event_picture_retention_days"):
            suggested = (field.get("description") or {}).get("suggested_value")
            if suggested:
                payload[name] = suggested
    return payload


def _field_names(step: dict[str, Any]) -> set[str]:
    return {f.get("name") for f in step.get("data_schema", [])}


def _current_options(entry: dict) -> dict:
    return dict(entry.get("options") or {})


def _assert_options_unchanged(ha, options_before: dict) -> None:
    unchanged = _current_options(ha.entries()[0]) == options_before
    assert unchanged, "The options draft must not be saved"


def test_options_flow_last_step_and_forward_only_navigation(ha, twon, entry) -> None:
    options_before = _current_options(entry)

    # Ground truth from the device: how many enabled relays the options
    # flow will offer steps for.
    relays = [s for s in twon.switch_caps() if s.get("enabled")]
    options = entry.get("options") or {}
    data = entry.get("data") or {}
    camera_enabled = options.get("enable_camera", data.get("enable_camera", True))
    steps = ["device"]
    if camera_enabled:
        steps.append("camera")
    steps.extend(["relay"] * len(relays))

    flow = ha.options_flow_start(entry["entry_id"])
    flow_id = flow["flow_id"]
    try:
        for index, step_id in enumerate(steps):
            assert flow["type"] == "form" and flow["step_id"] == step_id, flow
            assert flow["last_step"] is (index == len(steps) - 1)
            assert "go_back" not in _field_names(flow)
            assert _current_options(ha.entries()[0]) == options_before

            if step_id == "device":
                keypress_field = next(
                    field for field in flow["data_schema"]
                    if field.get("name") == "ring_on_keypress"
                )
                assert keypress_field.get("default") is options_before.get(
                    "ring_on_keypress", False
                )

            if step_id == "camera":
                # RTSP password stays masked and is never suggested (TASK-15).
                rtsp_pw = next(
                    f for f in flow["data_schema"] if f.get("name") == "rtsp_password"
                )
                assert rtsp_pw.get("selector", {}).get("text", {}).get("type") == "password"
                assert "suggested_value" not in (rtsp_pw.get("description") or {})

            if index == len(steps) - 1:
                # Never submit the saving step, including a device-only flow.
                break
            payload = _defaults_payload(flow)
            if step_id == "device":
                payload["name"] = f"{payload['name']} (draft)"
            flow = ha.options_flow_submit(flow_id, payload)
    finally:
        ha.options_flow_abort(flow_id)

    assert _current_options(ha.entries()[0]) == options_before


def test_options_flow_event_picture_retention_required(ha, entry) -> None:
    """Camera options reject saving pictures without retention, without saving."""
    options_before = _current_options(entry)
    data = entry.get("data") or {}
    if not options_before.get("enable_camera", data.get("enable_camera", True)):
        pytest.skip("camera is switched off in the entry options")
    flow = ha.options_flow_start(entry["entry_id"])
    flow_id = flow["flow_id"]
    try:
        assert flow["type"] == "form" and flow["step_id"] == "device", (
            "Expected the options Device form"
        )
        if "enable_camera" not in _field_names(flow):
            pytest.skip("device reports no camera")
        assert flow["last_step"] is False, "Never submit a final saving step"
        flow = ha.options_flow_submit(flow_id, _defaults_payload(flow))
        assert flow["type"] == "form" and flow["step_id"] == "camera", (
            "Expected the options Camera form"
        )
        assert {
            "save_event_pictures", "event_picture_retention_days"
        } <= _field_names(flow)
        _assert_options_unchanged(ha, options_before)
        assert flow["last_step"] is False, "Never submit a final saving step"

        payload = _defaults_payload(flow)
        payload["save_event_pictures"] = True
        payload.pop("event_picture_retention_days", None)
        flow = ha.options_flow_submit(flow_id, payload)
        assert flow["type"] == "form" and flow["step_id"] == "camera", (
            "Invalid retention must stay on the Camera form"
        )
        assert flow.get("errors", {}).get("event_picture_retention_days") == (
            "retention_required"
        )
        _assert_options_unchanged(ha, options_before)
    finally:
        ha.options_flow_abort(flow_id)

    _assert_options_unchanged(ha, options_before)


def test_grant_access_user_labels_match_directory(ha, twon, entry) -> None:
    """HA's user labels match dir/query, without saving or exposing user data."""
    named_users = [user for user in twon.dir_users() if user.get("name")]
    named_count = len(named_users)
    assert named_count > 0, f"Named directory users available: {named_count}"

    options_before = _current_options(entry)
    flow = ha.options_flow_start(entry["entry_id"])
    flow_id = flow["flow_id"]
    try:
        is_device_form = flow.get("type") == "form" and flow.get("step_id") == "device"
        assert is_device_form, "Expected the options device form"
        directory_ok = "directory_unavailable" not in (flow.get("errors") or {}).values()
        assert directory_ok, "HA could not load the directory"
        grant_field = next(
            (field for field in flow.get("data_schema", [])
             if field.get("name") == "grant_access_user"),
            {},
        )
        user_options = grant_field.get("selector", {}).get("select", {}).get("options", [])
        labels_by_uuid = {
            option["value"].lower(): option["label"]
            for option in user_options
            if isinstance(option, dict)
        }
        mismatched_count = sum(
            labels_by_uuid.get(user["uuid"].lower()) != user["name"]
            for user in named_users
        )
        assert mismatched_count == 0, (
            f"Directory label mismatches: {mismatched_count} of {named_count}"
        )
    finally:
        ha.options_flow_abort(flow_id)

    options_unchanged = _current_options(ha.entries()[0]) == options_before
    assert options_unchanged, "Aborting the directory check must not save options"
