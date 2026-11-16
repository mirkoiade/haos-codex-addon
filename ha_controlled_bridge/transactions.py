"""Narrow transactional operations for approved Home Assistant writes."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

try:
    from .policy import energy_validation_issue_types
except ImportError:  # bridge.py is also launched as a script by the add-on
    from policy import energy_validation_issue_types


class ApprovalError(RuntimeError):
    pass


async def approve_plan(
    plan: dict[str, Any], now: float, confirm_flow: bool,
    execute: Callable[[dict[str, Any], bool], Awaitable[None]],
) -> None:
    if plan.get("status") != "pending":
        raise ApprovalError("Plan is absent or already handled")
    if plan.get("expires", 0) < now:
        plan["status"] = "expired"
        raise ApprovalError("Plan expired")
    if plan.get("kind") == "replace_energy_source" and not confirm_flow:
        raise ApprovalError("Physical channel meaning was not confirmed")
    plan["status"] = "applying"
    try:
        await execute(plan, confirm_flow)
    except Exception:
        if plan.get("status") == "applying":
            plan["status"] = "failed"
        raise
    plan["status"] = "applied"


async def _registry_entry(ha: Any, entity_id: str) -> dict[str, Any] | None:
    entries = await ha.call("config/entity_registry/list")
    return next((entry for entry in entries if entry.get("entity_id") == entity_id), None)


async def apply_enable_entity(plan: dict[str, Any], ha: Any) -> None:
    entity_id = plan["entity_id"]
    current = await _registry_entry(ha, entity_id)
    if not current or current.get("disabled_by") != plan["before"]:
        raise RuntimeError("Registry changed since preview; create a new plan")
    try:
        await ha.call("config/entity_registry/update", {"entity_id": entity_id, "disabled_by": None})
        result = await _registry_entry(ha, entity_id)
        if result and result.get("disabled_by") is None:
            return
        raise RuntimeError("Entity registry readback did not match")
    except Exception as original:
        try:
            latest = await _registry_entry(ha, entity_id)
            if latest and latest.get("disabled_by") == plan["before"]:
                plan["status"] = "failed_unchanged"
                raise original
            if latest and latest.get("disabled_by") is None:
                # HA's API only permits disabling by the user; it cannot restore
                # disabled_by=integration. Preserve disabled behavior, report provenance change.
                await ha.call("config/entity_registry/update", {
                    "entity_id": entity_id, "disabled_by": "user",
                })
                restored = await _registry_entry(ha, entity_id)
                if restored and restored.get("disabled_by") == "user":
                    plan["status"] = "compensated_user_disabled"
                    raise original
            plan["status"] = "rollback_failed"
            raise RuntimeError("Enable failed; prior integration-disabled status cannot be restored through the supported API") from original
        except Exception as rollback_error:
            if plan.get("status") in {"failed_unchanged", "compensated_user_disabled"}:
                raise original
            if plan.get("status") != "rollback_failed":
                plan["status"] = "rollback_failed"
            raise rollback_error


async def apply_energy_source_replace(
    plan: dict[str, Any], ha: Any, candidate_report: Callable[[str], Awaitable[dict[str, Any]]],
) -> None:
    current = await ha.call("energy/get_prefs")
    if current != plan["before_prefs"]:
        raise RuntimeError("Energy preferences changed since preview; create a new plan")
    fresh = await candidate_report(plan["statistic_id"])
    if not fresh.get("eligible"):
        raise RuntimeError("Candidate no longer meets energy eligibility checks")
    after = plan["after_prefs"]
    payload = {key: after[key] for key in ("energy_sources", "device_consumption", "device_consumption_water") if key in after}
    try:
        await ha.call("energy/save_prefs", payload)
        if await ha.call("energy/get_prefs") != after:
            raise RuntimeError("Energy preferences readback did not match")
        validation = await ha.call("energy/validate")
        issues = energy_validation_issue_types(validation, plan["source_index"], plan["statistic_id"])
        if issues:
            raise RuntimeError("Energy validation reports candidate issue(s): " + ", ".join(issues))
    except Exception as original:
        before = plan["before_prefs"]
        restore = {key: before[key] for key in ("energy_sources", "device_consumption", "device_consumption_water") if key in before}
        try:
            await ha.call("energy/save_prefs", restore)
            if await ha.call("energy/get_prefs") != before:
                raise RuntimeError("Energy preferences rollback readback did not match")
        except Exception as rollback_error:
            plan["status"] = "rollback_failed"
            raise RuntimeError("Apply failed and Energy preferences rollback could not be verified") from rollback_error
        plan["status"] = "rolled_back"
        raise original
