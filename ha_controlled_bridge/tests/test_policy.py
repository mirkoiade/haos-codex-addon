import unittest

from ha_controlled_bridge.policy import energy_eligibility, replace_energy_source, validate_entity_id, ws_command


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.state = {"state": "123.4", "attributes": {
            "device_class": "energy", "state_class": "total_increasing",
            "unit_of_measurement": "kWh",
        }}
        self.metadata = {"has_sum": True, "unit_class": "energy"}

    def test_energy_candidate_requires_state_metadata_and_samples(self):
        ok, reasons = energy_eligibility(self.state, self.metadata, [{"change": 1.2}])
        self.assertTrue(ok, reasons)
        ok, reasons = energy_eligibility(self.state, self.metadata, [])
        self.assertFalse(ok)
        self.assertIn("no recorder samples are available in the checked period", reasons)

    def test_rejects_unavailable_or_wrong_classes(self):
        state = {"state": "unavailable", "attributes": self.state["attributes"]}
        ok, reasons = energy_eligibility(state, self.metadata, [{"change": 1}])
        self.assertFalse(ok)
        self.assertIn("entity has no usable current state", reasons)

    def test_preference_update_preserves_unrelated_values(self):
        prefs = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.old"}],
                 "device_consumption": [{"stat_consumption": "sensor.other"}]}
        result = replace_energy_source(prefs, 0, "sensor.new")
        self.assertEqual(result["energy_sources"][0]["stat_energy_from"], "sensor.new")
        self.assertEqual(result["device_consumption"], prefs["device_consumption"])
        self.assertEqual(prefs["energy_sources"][0]["stat_energy_from"], "sensor.old")

    def test_registry_writes_are_entity_allowlisted(self):
        self.assertEqual(validate_entity_id("sensor.a", {"sensor.a"}), "sensor.a")
        with self.assertRaises(PermissionError):
            validate_entity_id("sensor.b", {"sensor.a"})

    def test_websocket_command_allowlist_rejects_arbitrary_call(self):
        self.assertEqual(ws_command("energy/get_prefs", {})["type"], "energy/get_prefs")
        with self.assertRaises(PermissionError):
            ws_command("homeassistant/turn_off", {"entity_id": "switch.x"})


if __name__ == "__main__":
    unittest.main()
