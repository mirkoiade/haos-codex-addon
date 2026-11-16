"""New connector tests only; original bridge tests are not repeated."""
import importlib.util
import hashlib
import json
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "controlled_bridge_mcp.py"
SPEC = importlib.util.spec_from_file_location("controlled_bridge_mcp", PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def settings_from_args(args):
    if not args:
        return {}
    assert len(args) % 2 == 0
    return {args[index].removeprefix("mcp_servers.ha_controlled_bridge.").split("=")[0]:
            json.loads(args[index].split("=", 1)[1])
            for index in range(1, len(args), 2)}


class ControlledBridgeConnectorTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertEqual(bridge.bridge_mcp_args({}), [])
        self.assertEqual(bridge.bridge_mcp_env({}), {})
        self.assertEqual(bridge.bridge_mcp_args({"controlled_bridge_token": "x" * 40}), [])

    def test_missing_invalid_token_fails_closed(self):
        for token in ("", "short", "x" * 31, "x" * 513, "x" * 32 + "\n", 42):
            opts = {"controlled_bridge_enabled": True, "controlled_bridge_token": token}
            self.assertEqual(bridge.bridge_mcp_args(opts), [])
            self.assertEqual(bridge.bridge_mcp_env(opts), {})

    def test_exact_internal_target_and_approval_policy(self):
        token = "secret-placeholder-abcdefghijklmnopqrstuvwxyz-1234"
        opts = {"controlled_bridge_enabled": True, "controlled_bridge_token": token}
        args = bridge.bridge_mcp_args(opts)
        settings = settings_from_args(args)
        self.assertEqual(settings["url"], "http://17dc2992-ha-controlled-bridge:8765/mcp")
        self.assertEqual(bridge.BRIDGE_REPOSITORY_ID, hashlib.sha1(bridge.BRIDGE_REPOSITORY_URL.lower().encode()).hexdigest()[:8])
        self.assertEqual(settings["bearer_token_env_var"], bridge.TOKEN_ENV)
        self.assertEqual(settings["enabled_tools"], bridge.ALLOWED_TOOLS)
        self.assertEqual(settings["default_tools_approval_mode"], "approve")
        self.assertFalse(settings["required"])
        self.assertTrue(settings["enabled"])
        self.assertNotIn(token, " ".join(args))
        self.assertEqual(bridge.bridge_mcp_env(opts), {bridge.TOKEN_ENV: token})
        self.assertNotIn("danger-full-access", " ".join(args))

    def test_no_generic_or_approval_tools(self):
        self.assertEqual(len(set(bridge.ALLOWED_TOOLS)), 5)
        self.assertTrue(all(name.startswith(("inspect_", "energy_", "plan_"))
                            for name in bridge.ALLOWED_TOOLS))
        self.assertFalse(any("approve" in name or "exec" in name
                             for name in bridge.ALLOWED_TOOLS))


if __name__ == "__main__":
    unittest.main()
