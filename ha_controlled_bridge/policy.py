"""Pure policy helpers. No HA I/O and no filesystem access."""
from __future__ import annotations

import copy
import re
from typing import Any

ENTITY_ID_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
ENERGY_UNITS = {"Wh", "kWh", "MWh"}


def validate_entity_id(entity_id: str, allowlist: set[str]) -> str:
    if not ENTITY_ID_RE.fullmatch(entity_id):
        raise ValueError("Invalid entity_id")
    if entity_id not in allowlist:
        raise PermissionError("Entity is outside the configured allowlist")
    return entity_id


def energy_eligibility(
    state: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    samples: list[dict[str, Any]] | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not state or state.get("state") in (None, "unknown", "unavailable"):
        reasons.append("entity has no usable current state")
    attrs = (state or {}).get("attributes") or {}
    if attrs.get("device_class") != "energy":
        reasons.append("device_class must be energy")
    if attrs.get("state_class") not in {"total", "total_increasing"}:
        reasons.append("state_class must be total or total_increasing")
    if attrs.get("unit_of_measurement") not in ENERGY_UNITS:
        reasons.append("unit must be Wh, kWh, or MWh")
    if not metadata:
        reasons.append("recorder has no statistics metadata")
    else:
        if metadata.get("has_sum") is not True:
            reasons.append("recorder statistic does not support sum")
        if metadata.get("unit_class") != "energy":
            reasons.append("recorder unit_class is not energy")
    if not samples:
        reasons.append("no recorder samples are available in the checked period")
    return not reasons, reasons


def replace_energy_source(
    prefs: dict[str, Any], source_index: int, statistic_id: str
) -> dict[str, Any]:
    if not isinstance(source_index, int) or source_index < 0:
        raise ValueError("source_index must be a non-negative integer")
    if not ENTITY_ID_RE.fullmatch(statistic_id):
        raise ValueError("Invalid statistic_id")
    updated = copy.deepcopy(prefs)
    sources = updated.get("energy_sources")
    if not isinstance(sources, list) or source_index >= len(sources):
        raise ValueError("Energy source index does not exist")
    source = sources[source_index]
    if source.get("type") not in {"grid", "solar", "battery"}:
        raise ValueError("Only electrical energy sources can be changed")
    source["stat_energy_from"] = statistic_id
    return updated


def ws_command(command: str, args: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "get_states",
        "config/entity_registry/list",
        "config/auth/list",
        "config/device_registry/list",
        "config/entity_registry/update",
        "energy/get_prefs",
        "energy/save_prefs",
        "energy/validate",
        "recorder/get_statistics_metadata",
        "recorder/statistics_during_period",
    }
    if command not in allowed:
        raise PermissionError("WebSocket command is not allowlisted")
    return {"type": command, **args}
