# Codex CLI Worker - Controlled Bridge (TEST candidate)

Experimental parallel Worker, based on moryoav/home-assistant-codex v0.1.82.
It does NOT replace or upgrade the existing Worker.

Pinned source: ce05342ec6e9b8b18df8c7884f5cad4eb72f60a3.
The connector and patch files mirror worker_connector/ exactly.

The candidate has a unique Supervisor slug and manual boot, admin-only
Ingress, its own `apparmor.txt` based on the exact pinned upstream profile
(with only the profile name changed), Codex read-only sandbox, disabled
auto-saving, disabled browser verification, disabled automatic documentation
download, and the external MCP switched off by default. Its task directory is separate:
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

The candidate derives from the exact upstream 0.1.82 ARM64 image digest
sha256:9c4a4438cc504a54901113b9df34bda89c9fdf4e2f600b6592abae000c303b72. The digest was captured from the successful GitHub Actions
ARM64 build #43822677755. This is still a TEST candidate, not a deployed
production configuration.

## Bridge 0.1.82-bridge.3 — HAOS sandbox repair

The previous .2 candidate omitted `apparmor.txt` despite `apparmor: true`.
Supervisor therefore used the default AppArmor policy, which cannot grant the
narrow, separately confined Bubblewrap setup permissions from upstream. This
can produce `bwrap: Failed to make / slave: Permission denied` during the
Codex sandbox preflight. This release vendors the full upstream profile,
renaming only its outer label to `codex_cli_worker_bridge`. The nested
`/opt/codex-sandbox/bwrap.real` confinement stays unchanged. CI compares the
full profile against the pinned upstream source and parses it without loading
policy into the GitHub runner kernel.

This fixes an identified packaging regression; it is not a proof of Green
kernel support. Refresh the branch repository and UPDATE the candidate add-on
in the Home Assistant UI (do not merely restart the old container). Do not
switch to danger-full-access, disable AppArmor, or disable protection mode.
Test `read-only` first. If the preflight still fails, obtain the authenticated
Worker `/health` sandbox readiness details and logs without sharing secrets.
