# Worker 0.1.82 -> controlled bridge: offline connector candidate

Status: source patch only. NOT installed on Home Assistant Green, NOT published,
NOT an update to the existing Worker 0.1.82 installation. No live connectivity
or UI approval flow has been verified.

Upstream: moryoav/home-assistant-codex at exact revision
ce05342ec6e9b8b18df8c7884f5cad4eb72f60a3. The patch checks this revision
and expected source anchors, then adds one optional external MCP to the existing
two internal MCP configurations. It does not edit a generated config.toml.

## Safety design

- Keep Codex sandbox workspace-write and its normal on-request shell approval.
- Do not use danger-full-access, disable AppArmor, give Docker access or forward
  the SUPERVISOR_TOKEN.
- The bridge URL is fixed to the internal DNS name
  http://17dc2992-ha-controlled-bridge:8765/mcp for the BRANCH repository
  https://github.com/mirkoiade/haos-codex-addon#codex/haos-controlled-mcp-bridge.
  Supervisor hashes the *entire* registered repository URL, including #branch.
  Registration from the default URL (without #branch) would use e37e54d0,
  but the controlled bridge is not on main; do not mix these two URLs.
  Confirm the real installed hostname before enabling the connector.
- The Worker connector is off by default. It is enabled only if both the bool
  controlled_bridge_enabled and a 32-512-character dedicated ASCII bearer token
  in controlled_bridge_token are present.
- The token is read from private Supervisor app options. Only its env variable
  name (not its value) appears in Codex arguments. It is injected solely into
  the app-server child process, not config.toml, prompts or task command logs.
  The add-on option is declared password?; do not paste secrets into ChatGPT.
- Only five known bridge tools are exposed. The approval mode is approve for
  those bounded MCP calls, eliminating Codex's extra per-call Allow once prompt.
  MCP plan_* tools STAGE proposals only. They cannot commit a change.
  Every real HA edit still needs a separate human approval in the bridge's
  admin-only Supervisor Ingress page, with revalidation and rollback rules.
- The two existing Worker MCP servers remain unchanged.
- The add-on's host port mapping 8765 must remain OFF. Internal add-on networking
  does not require a host port mapping. The bridge's mcp_allowed_hosts option
  must explicitly allow 17dc2992-ha-controlled-bridge:8765.
- No arbitrary URL, HTTP headers, Supervisor credential, generic WebSocket
  execution or direct dashboard modification is exposed by this patch.
- WARNING: sandboxed shell tasks run in the same Worker container as Codex.
  Do not claim process environment credentials are inaccessible to all CLI
  subprocesses or exploit-free. This connector is NOT a hardened secret boundary.
  Keep the dedicated token narrowly useful, rotate if exposed, and do not use
  the Supervisor token. If strict separation from all Codex child processes is
  required, use a separately isolated broker, not this design.

## Offline build and verification

Use the new GitHub Actions workflow Worker bridge connector check. It checks
out precisely the pinned upstream revision, applies the patch, compiles the
patched sources, runs NEW connector tests, and validates the MCP configuration
against the actual pinned Codex CLI 0.165.0 binary. No Docker image is pushed.

The installed bridge hostname cannot be learned from GitHub; the expected
17dc2992 prefix must be checked against Supervisor on the real Green.
This workflow does not prove inter-container reachability or token negotiation.

The upstream config's image reference is removed when patching so that a
future candidate cannot silently pull the UNPATCHED upstream image. The patched
Dockerfile copies controlled_bridge_mcp.py into the image. Do not install a
candidate without separately approving its build, registration, credential
provisioning, explicit Host allowlist, and read-only connectivity checks.

## Remaining gates before any live change

1. Independently inspect the real Green's Supervisor add-on ID/hostname. If it
   does not equal 17dc2992_ha_controlled_bridge, do not use the fixed URL.
2. Review the bridge Ingress authorization and the token-handling threat model.
3. Explicitly approve an installation/test plan and a rollback/backup procedure.
4. Validate a read-only MCP connection first; stage any changes only afterward.
5. Keep real updates to Energy and Shelly entities behind Ingress approval.
