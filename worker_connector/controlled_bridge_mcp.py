"""Optional, pinned MCP registration for the HA controlled bridge.

No Home Assistant or Supervisor token is ever used here. The only credential
is the independent bridge bearer token; it is not inserted in CLI arguments or
written to the Codex config file. This module never opens a network connection.
"""
from __future__ import annotations

import json

BRIDGE_URL = "http://e37e54d0-ha-controlled-bridge:8765/mcp"
TOKEN_ENV = "HA_CONTROLLED_BRIDGE_MCP_TOKEN"
ALLOWED_TOOLS = [
    "inspect_shelly_energy_entities",
    "energy_get_prefs",
    "plan_enable_energy_entity",
    "plan_energy_source_replace",
    "plan_status",
]


def _token(options: dict) -> str:
    if options.get("controlled_bridge_enabled") is not True:
        return ""
    value = options.get("controlled_bridge_token")
    if not isinstance(value, str) or len(value) < 32 or len(value) > 512:
        return ""
    # Do not accept whitespace, control characters, or non-ASCII in bearer credentials.
    if any(not 33 <= ord(char) <= 126 for char in value):
        return ""
    return value


def bridge_mcp_args(options: dict) -> list[str]:
    """Configure only the five existing tools; the bridge itself gates writes."""
    if not _token(options):
        return []
    settings = {
        "url": BRIDGE_URL,
        "bearer_token_env_var": TOKEN_ENV,
        "enabled": True,
        "required": False,
        "enabled_tools": ALLOWED_TOOLS,
        "default_tools_approval_mode": "approve",
        "startup_timeout_sec": 15,
        "tool_timeout_sec": 120,
    }
    return [
        argument
        for name, value in settings.items()
        for argument in ("--config", f"mcp_servers.ha_controlled_bridge.{name}={json.dumps(value)}")
    ]


def bridge_mcp_env(options: dict) -> dict[str, str]:
    """Pass a dedicated credential only to the Codex app-server process."""
    token = _token(options)
    return {TOKEN_ENV: token} if token else {}
