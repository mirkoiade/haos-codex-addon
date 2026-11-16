# HA Controlled MCP Bridge (experimental)

This is an additive, manual-start Home Assistant app for testing a narrow MCP
bridge. It has not been installed on Home Assistant Green or published as an add-on.
Its ARM64 container is built and import-smoke-tested in CI only. It never mounts `/config`, `.storage`, or secrets files.

## Initial supported operations

Read-only MCP tools:
- inspect selected entity states and registry/device associations
- inspect current Energy preferences
- inspect recorder statistics metadata and a bounded sample window

Staged operations:
- request enabling the configured Shelly Pro EM50 energy entity IDs through
  `config/entity_registry/update`
- propose replacing one electrical Energy source statistic ID through
  `energy/get_prefs` / `energy/save_prefs`, only after current state,
  metadata and recorder samples pass eligibility checks

The add-on serves the MCP endpoint on optional port 8765 and a separate approval
page through Supervisor Ingress. A proposal is only a preview. An administrator
must approve it in Ingress; the approval handler re-reads current state and
preferences, checks the proposal is not stale, performs the exact allowlisted
call, reads back the result and rolls back the prior value if verification fails.
Energy source changes require an explicit human attestation in the approval UI
that the physical meter channel matches the displayed flow. Plans expire and are
kept only in memory; an audit record is written to the add-on's private data,
not to the HA configuration directory.

No generic WebSocket passthrough, service call, automation execution, device
action, restart, file edit, entity deletion, or `.storage` access is exposed.

## Security boundary and unavoidable privilege

The app uses the Supervisor-provided `SUPERVISOR_TOKEN` internally; it is never
returned by MCP, written to logs, or requested from the user. Official Supervisor
documentation says `homeassistant_api: true` provides the Core API proxy and
requests through it run as a Home Assistant administrator. That proxy does not
offer per-WebSocket-command scopes. The bridge therefore narrows its own command
allowlist and adds human approval, but a vulnerability in the add-on would still
have broad Core API authority. This is a real residual risk, not least-privilege
authorization.

`mcp_access_token` is a separate connector credential held in Supervisor app
options and checked by the MCP listener; it is not the HA token. It must be set
by an administrator and entered into the MCP host's secret store, never into a
conversation. `mcp_allowed_hosts` must list the exact MCP Host header(s).
Port mapping is disabled by default. If the MCP host is outside the LAN, a
separately approved VPN or authenticated reverse proxy is required; do not expose
the port directly to the public internet. The approval UI is on Ingress and
admin-only.

## Codex CLI Worker integration prerequisite

The currently deployed upstream Codex CLI Worker 0.1.82 from
`moryoav/home-assistant-codex` regenerates
`/data/codex-home/config.toml` when initializing and registers only its two
built-in MCP servers (`home_assistant` and `home_assistant_data`) in
`build_app_server_args()`. It has no add-on option for an extra remote MCP URL
and its token. Therefore installing this bridge alone will **not** expose its
tools to that Worker. Before attempting deployment, implement and review a
separate, narrowly scoped Worker-side connector (or another proven supported
MCP registration path), using protected credentials, appropriate network
access and no Supervisor-token forwarding. Do not rely on manually editing
the generated config.toml.

## Shelly/Energy procedure

1. Set candidate IDs to the two current Shelly Pro EM50 entities, set the MCP
   shared key and exact allowed host, then enable port mapping only on a trusted
   LAN/VPN path.
2. Use read-only inspection to confirm registry association, state, device class,
   state class, unit and statistics.
3. Stage enabling each entity. Review and approve it in Ingress. Re-read state
   and registry after each change.
4. Confirm the hardware wiring/meaning of each meter channel. Stage an Energy
   change only if eligibility succeeds; inspect the complete before/after diff,
   explicitly attest channel meaning, then approve in Ingress.
5. Verify Energy preferences, validation and statistics. Each plan captures the
   previous preferences for rollback. Registry rollback is limited by Home Assistant's API: `config/entity_registry/update` accepts `disabled_by: user` or `null`, but cannot restore `disabled_by: integration`. If an enable partially applies and must be compensated, the bridge re-disables as `user` and reports `compensated_user_disabled`; it never claims exact restoration. If that write/readback fails, status is `rollback_failed`. Energy preference rollback is verified with `energy/get_prefs`.

A zero-energy interval can be legitimate. This prototype requires recorder
samples, not a positive consumption value; physical flow semantics remain a
human confirmation because entity metadata cannot establish wiring direction.

## Explicitly out of scope for this prototype

Dashboard creation/editing and arbitrary YAML/configuration writes are not
implemented. They need separate, narrow adapters, their own preview/approval
format, and a documented rollback path; this prototype intentionally exposes no
generic file or WebSocket command. Add future operations as typed allowlisted
tools, never as a caller-supplied command string.

## Tests and limitations

From the repository root, run `python -m unittest discover -s ha_controlled_bridge/tests -v`. These tests
cover the pure allowlist and energy-eligibility policy; they do not connect to a
live Green or prove Supervisor Ingress identity, Core API proxy behavior, ARM64
runtime compatibility, or Home Assistant version compatibility. CI installs the pinned MCP SDK, validates the app manifest, smoke-tests the MCP transport API, runs policy tests plus Python compilation, and builds a Linux ARM64 container. A containerized import smoke test checks that the required modules are present in the built image. These checks do not prove Supervisor Ingress identity, the live Core API proxy, or runtime behavior on a real Green. Before any installation, the user must
review this branch, run the workflow, and explicitly approve installing/configuring
the app and networking. No token generation/export and no Green API call are part
of this branch change.
