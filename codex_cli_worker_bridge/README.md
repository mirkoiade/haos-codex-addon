# Codex CLI Worker - Controlled Bridge (TEST candidate)

Experimental parallel Worker, based on moryoav/home-assistant-codex v0.1.82.
It does NOT replace or upgrade the existing Worker.

Pinned source: ce05342ec6e9b8b18df8c7884f5cad4eb72f60a3.
The connector and patch files mirror worker_connector/ exactly.

The candidate has a unique Supervisor slug and manual boot, admin-only
Ingress, AppArmor, Codex read-only sandbox, disabled auto-saving, disabled
browser verification, disabled automatic documentation download, and the
external MCP switched off by default. Its task directory is separate:
  /config/codex_tasks_bridge

Important: the Home Assistant configuration mount remains writable like
upstream; Codex read-only mode is not full Docker filesystem isolation.
The Supervisor token remains a privileged Worker process capability.
Never use danger-full-access or disable AppArmor.

For this BRANCH only, register repository:
  https://github.com/mirkoiade/haos-codex-addon#codex/haos-controlled-mcp-bridge
Expected candidate ID: 17dc2992_codex_cli_worker_bridge
Expected bridge ID: 17dc2992_ha_controlled_bridge
Expected bridge DNS: 17dc2992-ha-controlled-bridge
Confirm real ID/hostname with Supervisor before enabling.

No installation, app start or secret provisioning is performed by GitHub CI.
The independent bearer token must be entered in each app's local options;
NEVER in chat or GitHub. Keep port 8765 unmapped. Test read-only tools first.
All writes stay behind bridge Ingress approval.

The candidate image derives from upstream image 0.1.82 tagged but not digest
pinned. Verify immutable base identity before any production use.
