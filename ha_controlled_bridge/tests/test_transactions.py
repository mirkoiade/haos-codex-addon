import asyncio
import copy
import unittest

from ha_controlled_bridge.policy import energy_validation_issue_types
from ha_controlled_bridge.transactions import (
    ApprovalError, apply_enable_entity, apply_energy_source_replace, approve_plan,
)


class FakeHA:
    def __init__(self, registry=None, prefs=None, validation=None, fail_commands=()):
        self.registry = registry or {"sensor.meter": {"entity_id": "sensor.meter", "disabled_by": "integration"}}
        self.prefs = prefs or {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.old"}],
                               "device_consumption": []}
        self.validation = validation or {"energy_sources": [[]], "device_consumption": [],
                                        "device_consumption_water": [], "device_consumption_gas": []}
        self.fail_commands = list(fail_commands)
        self.calls = []

    async def call(self, command, args=None):
        args = args or {}
        self.calls.append((command, copy.deepcopy(args)))
        if command in self.fail_commands:
            self.fail_commands.remove(command)
            raise RuntimeError("simulated API write failure")
        if command == "config/entity_registry/list":
            return list(self.registry.values())
        if command == "config/entity_registry/update":
            self.registry[args["entity_id"]]["disabled_by"] = args["disabled_by"]
            return {}
        if command == "energy/get_prefs":
            return copy.deepcopy(self.prefs)
        if command == "energy/save_prefs":
            self.prefs = copy.deepcopy(args)
            return {}
        if command == "energy/validate":
            return copy.deepcopy(self.validation)
        raise AssertionError("unexpected command: " + command)


class TransactionTests(unittest.TestCase):
    def test_energy_validate_uses_actual_nested_schema_and_rejects_candidate_issue(self):
        valid = {"energy_sources": [[], []], "device_consumption": [],
                 "device_consumption_water": [], "device_consumption_gas": []}
        self.assertEqual(energy_validation_issue_types(valid, 0, "sensor.meter"), [])
        issue = {"type": "entity_not_found",
                 "affected_entities": [["sensor.meter", "Grid import"], ["sensor.other", "Other"]]}
        self.assertEqual(energy_validation_issue_types(
            {"energy_sources": [[issue]], "device_consumption": []}, 0, "sensor.meter"),
            ["entity_not_found"])
        self.assertEqual(energy_validation_issue_types(
            {"energy_sources": [[issue]], "device_consumption": []}, 0, "sensor.unrelated"), [])
        with self.assertRaises(ValueError):
            energy_validation_issue_types({"energy_sources": "sensor.meter"}, 0, "sensor.meter")

    def test_approval_requires_pending_plan_and_physical_flow_and_expiration(self):
        async def run():
            calls = []
            async def execute(plan, confirm):
                calls.append(confirm)
            missing = {"status": "pending", "kind": "replace_energy_source", "expires": 20}
            with self.assertRaises(ApprovalError):
                await approve_plan(missing, 10, False, execute)
            self.assertEqual(missing["status"], "pending")
            expired = {"status": "pending", "kind": "enable_entity", "expires": 9}
            with self.assertRaises(ApprovalError):
                await approve_plan(expired, 10, True, execute)
            self.assertEqual(expired["status"], "expired")
            good = {"status": "pending", "kind": "replace_energy_source", "expires": 20}
            await approve_plan(good, 10, True, execute)
            self.assertEqual(good["status"], "applied")
            self.assertEqual(calls, [True])
        asyncio.run(run())

    def test_failed_enable_unchanged_does_not_attempt_impossible_integration_restore(self):
        async def run():
            ha = FakeHA(fail_commands=["config/entity_registry/update"])
            plan = {"entity_id": "sensor.meter", "before": "integration", "status": "applying"}
            with self.assertRaises(RuntimeError):
                await apply_enable_entity(plan, ha)
            self.assertEqual(plan["status"], "failed_unchanged")
            updates = [args for cmd, args in ha.calls if cmd == "config/entity_registry/update"]
            self.assertEqual(updates, [{"entity_id": "sensor.meter", "disabled_by": None}])
            self.assertNotIn("integration", [a.get("disabled_by") for a in updates])

    def test_enable_compensation_uses_supported_user_disabler_and_reports_provenance_change(self):
        async def run():
            ha = FakeHA()
            # First write takes effect but readback transiently fails; rollback then disables as user.
            original = ha.call
            reads = 0
            async def flaky(command, args=None):
                nonlocal reads
                if command == "config/entity_registry/list":
                    reads += 1
                    if reads == 2:
                        raise RuntimeError("simulated readback failure")
                return await original(command, args)
            ha.call = flaky
            plan = {"entity_id": "sensor.meter", "before": "integration", "status": "applying"}
            with self.assertRaises(RuntimeError):
                await apply_enable_entity(plan, ha)
            self.assertEqual(plan["status"], "compensated_user_disabled")
            self.assertEqual(ha.registry["sensor.meter"]["disabled_by"], "user")
            updates = [args for cmd, args in ha.calls if cmd == "config/entity_registry/update"]
            self.assertEqual(updates[-1]["disabled_by"], "user")
        asyncio.run(run())

    def test_enable_compensation_failure_is_reported(self):
        async def run():
            ha = FakeHA()
            original = ha.call
            reads = 0
            async def readback_fails_once(command, args=None):
                nonlocal reads
                if command == "config/entity_registry/list":
                    reads += 1
                    if reads == 2:
                        raise RuntimeError("simulated readback failure")
                if command == "config/entity_registry/update" and args.get("disabled_by") == "user":
                    raise RuntimeError("compensation denied")
                return await original(command, args)
            ha.call = readback_fails_once
            plan = {"entity_id": "sensor.meter", "before": "integration", "status": "applying"}
            with self.assertRaises(RuntimeError):
                await apply_enable_entity(plan, ha)
            self.assertEqual(plan["status"], "rollback_failed")
        asyncio.run(run())

    def test_energy_write_with_clean_structured_validation_succeeds(self):
        async def run():
            before = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.old"}],
                      "device_consumption": []}
            after = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.meter"}],
                     "device_consumption": []}
            ha = FakeHA(prefs=before, validation={"energy_sources": [[]], "device_consumption": [],
                                                  "device_consumption_water": [], "device_consumption_gas": []})
            plan = {"before_prefs": before, "after_prefs": after, "statistic_id": "sensor.meter",
                    "source_index": 0, "status": "applying"}
            async def candidate(_):
                return {"eligible": True}
            await apply_energy_source_replace(plan, ha, candidate)
            self.assertEqual(ha.prefs, after)
            self.assertEqual(plan["status"], "applying")
        asyncio.run(run())

    def test_energy_validation_error_rolls_preferences_back(self):
        async def run():
            before = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.old"}],
                      "device_consumption": []}
            after = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.meter"}],
                     "device_consumption": []}
            bad = {"energy_sources": [[{"type": "entity_not_found",
                    "affected_entities": [["sensor.meter", "Grid"]]}]], "device_consumption": []}
            ha = FakeHA(prefs=before, validation=bad)
            plan = {"before_prefs": before, "after_prefs": after, "statistic_id": "sensor.meter",
                    "source_index": 0, "status": "applying"}
            async def candidate(_):
                return {"eligible": True}
            with self.assertRaisesRegex(RuntimeError, "candidate issue"):
                await apply_energy_source_replace(plan, ha, candidate)
            self.assertEqual(ha.prefs, before)
            self.assertEqual(plan["status"], "rolled_back")
            self.assertEqual(sum(command == "energy/save_prefs" for command, _ in ha.calls), 2)
        asyncio.run(run())

    def test_failed_energy_write_rolls_back_and_reports_unverifiable_rollback(self):
        async def run():
            before = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.old"}],
                      "device_consumption": []}
            after = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.meter"}],
                     "device_consumption": []}
            # First save fails, and the compensation save is also made to fail.
            ha = FakeHA(prefs=before, fail_commands=["energy/save_prefs", "energy/save_prefs"])
            plan = {"before_prefs": before, "after_prefs": after, "statistic_id": "sensor.meter",
                    "source_index": 0, "status": "applying"}
            async def candidate(_):
                return {"eligible": True}
            with self.assertRaises(RuntimeError):
                await apply_energy_source_replace(plan, ha, candidate)
            self.assertEqual(plan["status"], "rollback_failed")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
