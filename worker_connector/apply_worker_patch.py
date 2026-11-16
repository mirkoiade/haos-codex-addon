"""Fail-closed offline patch for the pinned upstream Codex CLI Worker 0.1.82.

Usage: python worker_connector/apply_worker_patch.py <upstream checkout>
The checkout must be the exact public upstream revision below. This script
does not install anything, contact Home Assistant, or read real credentials.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

UPSTREAM_SHA = "ce05342ec6e9b8b18df8c7884f5cad4eb72f60a3"


def replace_once(content: str, before: str, after: str, path: Path) -> str:
    if content.count(before) != 1:
        raise RuntimeError(f"Upstream anchor mismatch in {path.name}: {before[:75]!r}")
    return content.replace(before, after, 1)


def apply(upstream: Path) -> None:
    upstream = upstream.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != UPSTREAM_SHA:
        raise RuntimeError("Refusing unexpected upstream revision")
    root = upstream / "codex-cli-worker"
    source = Path(__file__).resolve().parent / "controlled_bridge_mcp.py"
    changes = {
        "server.py": [
            (
                "from ha_data import HomeAssistantData\n",
                "from ha_data import HomeAssistantData\n"
                "from controlled_bridge_mcp import bridge_mcp_args, bridge_mcp_env\n",
            ),
            (
                '"HA_DATA_SOCKET"):\n',
                '"HA_DATA_SOCKET", "HA_CONTROLLED_BRIDGE_MCP_TOKEN"):\n',
            ),
            (
                '*verification_mcp_args(), *data_mcp_args()]\n',
                '*verification_mcp_args(), *data_mcp_args(), '
                '*bridge_mcp_args(read_options())]\n',
            ),
            (
                'env={**codex_env(), "HA_VERIFICATION_CAPABILITY": verification_capability, "HA_DATA_CAPABILITY": data_capability},\n',
                'env={**codex_env(), "HA_VERIFICATION_CAPABILITY": verification_capability, '
                '"HA_DATA_CAPABILITY": data_capability, **bridge_mcp_env(options)},\n',
            ),
        ],
        "config.yaml": [
            (
                'version: "0.1.82"\n',
                'version: "0.1.82-bridge.1"\n',
            ),
            (
                "image: ghcr.io/moryoav/codex-cli-worker\n",
                "# No upstream image: candidate must build from the patched Dockerfile.\n",
            ),
            (
                "  ha_url: http://homeassistant:8123\nschema:\n",
                "  ha_url: http://homeassistant:8123\n"
                "  controlled_bridge_enabled: false\n"
                '  controlled_bridge_token: ""\n'
                "schema:\n",
            ),
            (
                "  HA_TOKEN: password?\n",
                "  HA_TOKEN: password?\n"
                "  controlled_bridge_enabled: bool\n"
                "  controlled_bridge_token: password?\n",
            ),
        ],
        "Dockerfile": [
            (
                "COPY server.py /\n",
                "COPY server.py controlled_bridge_mcp.py /\n",
            ),
        ],
    }
    # Validate ALL expected anchors before modifying any tracked file.
    patched = {}
    for filename, replacements in changes.items():
        path = root / filename
        result = path.read_text(encoding="utf-8")
        for before, after in replacements:
            result = replace_once(result, before, after, path)
        patched[path] = result
    dest = root / "controlled_bridge_mcp.py"
    if dest.exists():
        raise RuntimeError("Refusing to overwrite an existing connector")
    for path, content in patched.items():
        path.write_text(content, encoding="utf-8")
    shutil.copyfile(source, dest)
    print("Pinned worker patched. No image built or deployed.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: apply_worker_patch.py <upstream-checkout>")
    apply(Path(sys.argv[1]))
