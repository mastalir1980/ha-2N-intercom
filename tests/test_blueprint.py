"""Offline YAML and template checks for the doorbell notification blueprint."""

from __future__ import annotations

import types
import unittest

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import yaml

from _stubs import REPO_ROOT


class BlueprintLoader(yaml.SafeLoader):
    """Keep HA input tags while validating the rest as safe YAML."""


BlueprintLoader.add_constructor("!input", lambda loader, node: {"input": loader.construct_scalar(node)})


class DoorbellBlueprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (
            REPO_ROOT / "blueprints" / "doorbell_notification_answer_hangup.yaml"
        ).read_text(encoding="utf-8")
        cls.blueprint = yaml.load(cls.source, Loader=BlueprintLoader)

    def setUp(self) -> None:
        self.env = NativeEnvironment(undefined=StrictUndefined)

    def _state(self, state, **attributes):
        return types.SimpleNamespace(state=state, attributes=attributes)

    def _ring_condition(self, old, new):
        template = self.blueprint["condition"][0]["value_template"]
        return self.env.from_string(template).render(
            trigger=types.SimpleNamespace(from_state=old, to_state=new)
        )

    def test_selects_only_2n_doorbell_events(self) -> None:
        inputs = self.blueprint["blueprint"]["input"]
        self.assertEqual(inputs["doorbell_entity"]["selector"]["entity"]["filter"], [{
            "domain": "event", "integration": "2n_intercom", "device_class": "doorbell",
        }])
        self.assertNotIn("call_state_entity", inputs)
        self.assertNotIn("camera_entity", inputs)
        trigger = self.blueprint["trigger"][0]
        self.assertEqual(trigger["platform"], "state")
        self.assertEqual(trigger["entity_id"], {"input": "doorbell_entity"})
        self.assertNotIn("to", trigger)
        self.assertNotIn("replace(", self.source)

    def test_first_and_subsequent_ring_timestamp_changes_trigger(self) -> None:
        new = self._state("2026-10-18T10:00:00+00:00", event_type="ring")
        for old in (
            self._state("unknown"),
            self._state("2026-10-18T09:59:00+00:00", event_type="ring"),
        ):
            with self.subTest(old=old.state):
                self.assertTrue(self._ring_condition(old, new))

    def test_startup_restore_availability_and_attribute_updates_do_not_trigger(self) -> None:
        ring = self._state("2026-10-18T10:00:00+00:00", event_type="ring")
        for old, new in (
            (None, ring),
            (self._state("unavailable"), ring),
            (ring, self._state("unknown")),
            (ring, self._state("unavailable")),
            (ring, None),
            (ring, self._state(ring.state, event_type="ring", caller_name="Visitor")),
            (self._state("unknown"), self._state(ring.state, event_type="other")),
            (self._state("unknown"), self._state(ring.state, event_type="ring", restored=True)),
        ):
            with self.subTest(old=old, new=new):
                self.assertFalse(self._ring_condition(old, new))

    def _resolve_device(self, *, camera=True, session=True):
        states = {
            "event.custom_button": types.SimpleNamespace(domain="event", attributes={}),
            "sensor.renamed_call": types.SimpleNamespace(
                domain="sensor", attributes={"active_session_id": "session-one"} if session else {}
            ),
            "sensor.registration": types.SimpleNamespace(domain="sensor", attributes={}),
            "camera.renamed_live": types.SimpleNamespace(domain="camera", attributes={}),
            "camera.unrelated_integration": types.SimpleNamespace(domain="camera", attributes={}),
            "sensor.other_intercom": types.SimpleNamespace(
                domain="sensor", attributes={"active_session_id": "session-two"}
            ),
            "camera.other_intercom": types.SimpleNamespace(domain="camera", attributes={}),
        }
        for entity_id, state in states.items():
            state.entity_id = entity_id
        device_entities = [
            "event.custom_button", "sensor.renamed_call", "sensor.registration",
            "camera.unrelated_integration",
        ]
        if camera:
            device_entities.append("camera.renamed_live")
        self.env.globals.update(
            device_id=lambda eid: "device-one" if eid == "event.custom_button" else None,
            device_entities=lambda device: device_entities if device == "device-one" else [],
            integration_entities=lambda integration: [
                eid for eid in states if eid != "camera.unrelated_integration"
            ] if integration == "2n_intercom" else [],
            config_entry_id=lambda eid: "entry-one" if eid == "event.custom_button" else None,
            expand=lambda eids: [states[eid] for eid in eids],
            state_attr=lambda eid, attr: states[eid].attributes.get(attr),
        )
        variables = {"trigger": types.SimpleNamespace(entity_id="event.custom_button")}
        for action in self.blueprint["action"]:
            for key, template in action.get("variables", {}).items():
                variables[key] = self.env.from_string(template).render(variables)
            if "if" in action:
                invalid = self.env.from_string(action["if"][0]["value_template"]).render(variables)
                if invalid:
                    self.assertTrue(action["then"][0]["error"])
                    self.assertIn("call state", action["then"][0]["stop"])
                    return variables, False
        return variables, True

    def test_renamed_entities_and_service_target_belong_to_trigger_device(self) -> None:
        variables, resolved = self._resolve_device()
        self.assertTrue(resolved)
        self.assertEqual(variables["call_state_entities"], ["sensor.renamed_call"])
        self.assertEqual(variables["camera_entities"], ["camera.renamed_live"])
        self.assertEqual(variables["session_id"], "session-one")
        self.assertEqual(variables["config_entry"], "entry-one")
        notification = next(a for a in self.blueprint["action"] if "service" in a)
        self.assertEqual(
            self.env.from_string(notification["data"]["data"]["image"]).render(variables),
            "/api/camera_proxy/camera.renamed_live",
        )
        choices = self.blueprint["action"][-1]["choose"]
        for choice in choices:
            service = choice["sequence"][0]
            self.assertIn(service["service"], ("2n_intercom.answer_call", "2n_intercom.hangup_call"))
            self.assertEqual(
                self.env.from_string(service["data"]["config_entry_id"]).render(variables),
                "entry-one",
            )
            self.assertEqual(
                self.env.from_string(service["data"]["session_id"]).render(variables),
                "session-one",
            )

    def test_missing_camera_or_session_surfaces_a_clear_error(self) -> None:
        for camera, session in ((False, True), (True, False)):
            with self.subTest(camera=camera, session=session):
                _, resolved = self._resolve_device(camera=camera, session=session)
                self.assertFalse(resolved)


if __name__ == "__main__":
    unittest.main()
