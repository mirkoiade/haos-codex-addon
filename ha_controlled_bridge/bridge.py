from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import websockets
import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

from policy import energy_eligibility, replace_energy_source, validate_entity_id, ws_command

OPTIONS = json.loads(Path("/data/options.json").read_text())
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
MCP_TOKEN = OPTIONS.get("mcp_access_token", "")
if MCP_TOKEN and len(MCP_TOKEN) < 32:
    raise RuntimeError("MCP access key must be at least 32 characters")
ENTITY_ALLOWLIST = set(OPTIONS.get("energy_candidate_entity_ids", []))
PLANS: dict[str, dict[str, Any]] = {}
PLAN_TTL = 900
INGRESS_CSRF = secrets.token_urlsafe(32)
_ws_id = 0


class HAClient:
    async def call(self, command: str, args: dict[str, Any] | None = None) -> Any:
        if not SUPERVISOR_TOKEN:
            raise RuntimeError("Supervisor API token is not available")
        global _ws_id
        async with websockets.connect("ws://supervisor/core/websocket", open_timeout=10) as ws:
            await ws.recv()
            await ws.send(json.dumps({"type": "auth", "access_token": SUPERVISOR_TOKEN}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError("Home Assistant API authentication failed")
            _ws_id += 1
            message_id = _ws_id
            await ws.send(json.dumps({"id": message_id, **ws_command(command, args or {})}))
            async with asyncio.timeout(20):
                while True:
                    reply = json.loads(await ws.recv())
                    if reply.get("id") != message_id:
                        continue
                    if not reply.get("success"):
                        error = reply.get("error", {})
                        raise RuntimeError(f"Home Assistant API error: {error.get('code', 'unknown')}")
                    return reply.get("result")


ha = HAClient()
mcp = MCPServer("HA Controlled Bridge")


def _states_by_id(states: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    return next((x for x in states if x.get("entity_id") == entity_id), None)


def _metadata_by_id(metadata: Any, statistic_id: str) -> dict[str, Any] | None:
    items = metadata.get("statistics", []) if isinstance(metadata, dict) else metadata
    if isinstance(items, dict):
        return items.get(statistic_id)
    return next((x for x in (items or []) if x.get("statistic_id") == statistic_id), None)


async def _candidate_report(entity_id: str) -> dict[str, Any]:
    validate_entity_id(entity_id, ENTITY_ALLOWLIST)
    states, registry, devices, metadata, samples = await asyncio.gather(
        ha.call("get_states"),
        ha.call("config/entity_registry/list"),
        ha.call("config/device_registry/list"),
        ha.call("recorder/get_statistics_metadata", {"statistic_ids": [entity_id]}),
        ha.call("recorder/statistics_during_period", {
            "statistic_ids": [entity_id],
            "start_time": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "period": "hour",
            "types": ["sum", "change"],
        }),
    )
    state = _states_by_id(states, entity_id)
    reg_entry = next((x for x in registry if x.get("entity_id") == entity_id), None)
    device_by_id = {x["id"]: x for x in devices}
    device = device_by_id.get((reg_entry or {}).get("device_id"))
    meta = _metadata_by_id(metadata, entity_id)
    series = samples.get(entity_id, []) if isinstance(samples, dict) else []
    eligible, reasons = energy_eligibility(state, meta, series)
    raw_value = (state or {}).get("state")
    try:
        safe_value = str(float(raw_value))
    except (TypeError, ValueError):
        safe_value = raw_value if raw_value in {"unknown", "unavailable"} else "[non-numeric state redacted]"
    attrs = (state or {}).get("attributes") or {}
    safe_state = None if state is None else {
        "entity_id": entity_id,
        "state": safe_value,
        "last_changed": state.get("last_changed"),
        "last_updated": state.get("last_updated"),
        "attributes": {key: attrs[key] for key in (
            "device_class", "state_class", "unit_of_measurement", "restored"
        ) if key in attrs},
    }
    safe_registry = None if reg_entry is None else {
        key: reg_entry[key] for key in ("entity_id", "platform", "device_id", "disabled_by")
        if key in reg_entry
    }
    safe_device = None if device is None else {
        key: device[key] for key in ("id", "manufacturer", "model")
        if key in device
    }
    safe_meta = None if meta is None else {
        key: meta[key] for key in (
            "statistic_id", "has_sum", "has_mean", "unit_class", "unit_of_measurement"
        ) if key in meta
    }
    return {
        "entity_id": entity_id,
        "state": safe_state,
        "entity_registry": safe_registry,
        "device": safe_device,
        "statistics_metadata": safe_meta,
        "sample_count": len(series),
        "eligible": eligible,
        "reasons": reasons,
    }


@mcp.tool()
async def inspect_shelly_energy_entities() -> dict[str, Any]:
    """Read current state, registry/device association, metadata and seven-day statistics for the configured Shelly energy IDs."""
    return {"entities": [await _candidate_report(entity_id) for entity_id in sorted(ENTITY_ALLOWLIST)]}


@mcp.tool()
async def energy_get_prefs() -> dict[str, Any]:
    """Read the current Energy dashboard preferences using the official Home Assistant WebSocket command."""
    return await ha.call("energy/get_prefs")


@mcp.tool()
async def plan_enable_energy_entity(entity_id: str) -> dict[str, Any]:
    """Stage enabling one configured Shelly energy entity. An administrator must approve it in the add-on Ingress page."""
    validate_entity_id(entity_id, ENTITY_ALLOWLIST)
    entries = await ha.call("config/entity_registry/list")
    entry = next((x for x in entries if x.get("entity_id") == entity_id), None)
    if not entry:
        raise ValueError("Entity is not present in the entity registry")
    before = entry.get("disabled_by")
    if before is None:
        return {"status": "already_enabled", "entity_id": entity_id}
    if before != "integration":
        raise ValueError("Only entities disabled by their integration may be enabled by this plan")
    plan_id = secrets.token_urlsafe(18)
    PLANS[plan_id] = {
        "id": plan_id, "kind": "enable_entity", "status": "pending",
        "expires": time.time() + PLAN_TTL, "entity_id": entity_id,
        "before": before, "after": None,
    }
    _audit("plan_created", {"id": plan_id, "kind": "enable_entity", "entity_id": entity_id})
    return {"status": "pending_human_approval", "plan_id": plan_id, "expires_in_seconds": PLAN_TTL}


@mcp.tool()
async def plan_energy_source_replace(source_index: int, statistic_id: str) -> dict[str, Any]:
    """Stage replacing one electrical Energy source only after sensor eligibility and recorder data pass. Physical channel meaning must be confirmed in the approval UI."""
    validate_entity_id(statistic_id, ENTITY_ALLOWLIST)
    report = await _candidate_report(statistic_id)
    if not report["eligible"]:
        return {"status": "not_eligible", "entity_report": report}
    prefs = await ha.call("energy/get_prefs")
    updated = replace_energy_source(prefs, source_index, statistic_id)
    source_before = prefs["energy_sources"][source_index]
    source_after = updated["energy_sources"][source_index]
    plan_id = secrets.token_urlsafe(18)
    PLANS[plan_id] = {
        "id": plan_id, "kind": "replace_energy_source", "status": "pending",
        "expires": time.time() + PLAN_TTL, "before_prefs": prefs,
        "after_prefs": updated, "source_index": source_index,
        "statistic_id": statistic_id, "source_before": source_before,
        "source_after": source_after,
    }
    _audit("plan_created", {"id": plan_id, "kind": "replace_energy_source",
                            "source_index": source_index, "statistic_id": statistic_id})
    return {"status": "pending_human_approval", "plan_id": plan_id,
            "source_before": source_before, "source_after": source_after,
            "eligibility": report, "physical_flow_confirmation_required": True}


@mcp.tool()
async def plan_status(plan_id: str) -> dict[str, Any]:
    """Read the status of a staged change. This tool cannot approve or apply a plan."""
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError("Plan not found or expired")
    return {k: v for k, v in plan.items() if k not in {"before_prefs", "after_prefs"}}


def _audit(event: str, details: dict[str, Any]) -> None:
    Path("/data").mkdir(exist_ok=True)
    with Path("/data/audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                            "event": event, **details}, ensure_ascii=True) + "\n")


async def _registry_entry(entity_id: str) -> dict[str, Any] | None:
    items = await ha.call("config/entity_registry/list")
    return next((x for x in items if x.get("entity_id") == entity_id), None)


async def _apply(plan: dict[str, Any], confirm_flow: bool) -> None:
    if plan["kind"] == "enable_entity":
        current = await _registry_entry(plan["entity_id"])
        if not current or current.get("disabled_by") != plan["before"]:
            raise RuntimeError("Registry changed since preview; create a new plan")
        try:
            await ha.call("config/entity_registry/update", {
                "entity_id": plan["entity_id"], "disabled_by": None,
            })
            result = await _registry_entry(plan["entity_id"])
            if not result or result.get("disabled_by") is not None:
                raise RuntimeError("Entity registry readback did not match")
        except Exception as original:
            try:
                await ha.call("config/entity_registry/update", {
                    "entity_id": plan["entity_id"], "disabled_by": plan["before"],
                })
                restored = await _registry_entry(plan["entity_id"])
                if not restored or restored.get("disabled_by") != plan["before"]:
                    raise RuntimeError("Registry rollback readback did not match")
            except Exception as rollback_error:
                plan["status"] = "rollback_failed"
                raise RuntimeError("Enable failed and registry rollback verification failed") from rollback_error
            raise original
    elif plan["kind"] == "replace_energy_source":
        if not confirm_flow:
            raise ValueError("Physical meter-channel meaning was not confirmed")
        current = await ha.call("energy/get_prefs")
        if current != plan["before_prefs"]:
            raise RuntimeError("Energy preferences changed since preview; create a new plan")
        fresh = await _candidate_report(plan["statistic_id"])
        if not fresh["eligible"]:
            raise RuntimeError("Candidate no longer meets energy eligibility checks")
        after = plan["after_prefs"]
        payload = {k: after[k] for k in ("energy_sources", "device_consumption", "device_consumption_water")
                   if k in after}
        try:
            await ha.call("energy/save_prefs", payload)
            actual = await ha.call("energy/get_prefs")
            if actual != after:
                raise RuntimeError("Energy preferences readback did not match")
            validation = await ha.call("energy/validate")
            if plan["statistic_id"] in json.dumps(validation):
                raise RuntimeError("Energy validation reports an issue for the candidate")
        except Exception:
            before = plan["before_prefs"]
            restore = {k: before[k] for k in ("energy_sources", "device_consumption", "device_consumption_water")
                       if k in before}
            await ha.call("energy/save_prefs", restore)
            if await ha.call("energy/get_prefs") != before:
                plan["status"] = "rollback_failed"
                raise RuntimeError("Apply failed and rollback verification failed")
            plan["status"] = "rolled_back"
            raise
    else:
        raise PermissionError("Unknown staged operation")


async def _is_ingress_admin(request: Request) -> bool:
    if not request.client or request.client.host != "172.30.32.2":
        return False
    user_id = request.headers.get("x-remote-user-id")
    if not user_id:
        return False
    try:
        result = await ha.call("config/auth/list")
    except Exception:
        return False
    users = result.get("users", []) if isinstance(result, dict) else []
    return any(
        user.get("id") == user_id and (
            user.get("is_owner") is True or (
                user.get("is_active") is True and
                "system-admin" in (user.get("group_ids") or [])
            )
        )
        for user in users
    )


async def _pending(request: Request) -> JSONResponse:
    if not await _is_ingress_admin(request):
        return JSONResponse({"error": "Ingress proxy required"}, status_code=403)
    now = time.time()
    for plan_id, plan in list(PLANS.items()):
        if plan["expires"] < now and plan["status"] == "pending":
            plan["status"] = "expired"
    return JSONResponse([{
        "id": p["id"], "kind": p["kind"], "status": p["status"],
        "expires": datetime.fromtimestamp(p["expires"], timezone.utc).isoformat(),
        "entity_id": p.get("entity_id"), "before": p.get("before"),
        "source_before": p.get("source_before"), "source_after": p.get("source_after"),
    } for p in PLANS.values()])


async def _approve(request: Request) -> JSONResponse:
    if not await _is_ingress_admin(request):
        return JSONResponse({"error": "Ingress proxy required"}, status_code=403)
    if request.headers.get("x-ha-bridge-csrf", "") != INGRESS_CSRF:
        return JSONResponse({"error": "Invalid approval session"}, status_code=403)
    payload = await request.json()
    plan = PLANS.get(str(payload.get("plan_id", "")))
    if not plan or plan["status"] != "pending" or plan["expires"] < time.time():
        return JSONResponse({"error": "Plan is absent, expired or already handled"}, status_code=409)
    confirm_flow = payload.get("confirm_physical_flow") is True
    if plan["kind"] == "replace_energy_source" and not confirm_flow:
        return JSONResponse({"error": "Confirm the physical channel meaning first"}, status_code=400)
    plan["status"] = "applying"
    try:
        await _apply(plan, confirm_flow)
        plan["status"] = "applied"
        _audit("plan_applied", {"id": plan["id"], "kind": plan["kind"]})
        return JSONResponse({"status": "applied", "plan_id": plan["id"]})
    except Exception as err:
        if plan["status"] != "rolled_back":
            plan["status"] = "failed"
        _audit("plan_failed", {"id": plan["id"], "kind": plan["kind"],
                               "error": type(err).__name__})
        return JSONResponse({"status": plan["status"], "error": str(err)}, status_code=409)


async def _reject(request: Request) -> JSONResponse:
    if not await _is_ingress_admin(request):
        return JSONResponse({"error": "Ingress proxy required"}, status_code=403)
    if request.headers.get("x-ha-bridge-csrf", "") != INGRESS_CSRF:
        return JSONResponse({"error": "Invalid approval session"}, status_code=403)
    payload = await request.json()
    plan = PLANS.get(str(payload.get("plan_id", "")))
    if not plan or plan["status"] != "pending":
        return JSONResponse({"error": "Plan is absent or already handled"}, status_code=409)
    plan["status"] = "rejected"
    _audit("plan_rejected", {"id": plan["id"], "kind": plan["kind"]})
    return JSONResponse({"status": "rejected"})


UI = """<!doctype html><meta charset=utf-8><meta name=csrf-token content=CSRF_PLACEHOLDER><title>HA Bridge approvals</title>
<h1>Richieste di modifica Home Assistant</h1>
<p>Approva soltanto dopo aver controllato il prima/dopo. Le scritture partono solo dal pulsante qui sotto.</p>
<div id=items>Caricamento…</div>
<script>
async function refresh(){
 const r=await fetch('api/pending'); const items=await r.json();
 document.getElementById('items').innerHTML='';
 for(const p of items){
  const d=document.createElement('section'); d.style='border:1px solid #888;padding:1em;margin:1em 0';
  d.innerHTML='<h2>'+p.kind+' — '+p.status+'</h2><pre></pre>';
  d.querySelector('pre').textContent=JSON.stringify(p,null,2);
  if(p.status==='pending'){
   if(p.kind==='replace_energy_source') d.insertAdjacentHTML('beforeend','<label><input type=checkbox class=flow> Confermo che il canale fisico corrisponde alla sorgente e al flusso energetico mostrati</label> ');
   d.insertAdjacentHTML('beforeend','<button class=approve>Approva ed esegui</button> <button class=reject>Rifiuta</button>');
   d.querySelector('.approve').onclick=async()=>{const c=d.querySelector('.flow'); const x=await fetch('api/approve',{method:'POST',headers:{'Content-Type':'application/json','X-HA-Bridge-CSRF':document.querySelector('[name=csrf-token]').content},body:JSON.stringify({plan_id:p.id,confirm_physical_flow:!c||c.checked})}); alert(JSON.stringify(await x.json()));refresh();};
   d.querySelector('.reject').onclick=async()=>{await fetch('api/reject',{method:'POST',headers:{'Content-Type':'application/json','X-HA-Bridge-CSRF':document.querySelector('[name=csrf-token]').content},body:JSON.stringify({plan_id:p.id})});refresh();};
  }
  document.getElementById('items').appendChild(d);
 }
}
refresh(); setInterval(refresh,5000);
</script>"""


async def _home(request: Request) -> HTMLResponse:
    if not await _is_ingress_admin(request):
        return HTMLResponse("Supervisor Ingress required", status_code=403)
    return HTMLResponse(UI.replace("CSRF_PLACEHOLDER", INGRESS_CSRF))


ui_app = Starlette(routes=[
    Route("/", _home),
    Route("/api/pending", _pending),
    Route("/api/approve", _approve, methods=["POST"]),
    Route("/api/reject", _reject, methods=["POST"]),
])


class MCPAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not MCP_TOKEN:
            return PlainTextResponse("MCP access is not configured", status_code=503)
        auth = request.headers.get("authorization", "")
        expected = "Bearer " + MCP_TOKEN
        if not secrets.compare_digest(auth, expected):
            return PlainTextResponse("Unauthorized", status_code=401)
        return await call_next(request)


def _mcp_asgi():
    hosts = OPTIONS.get("mcp_allowed_hosts", [])
    if not hosts:
        hosts = ["127.0.0.1:8765", "localhost:8765", "[::1]:8765"]
    security = TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=[])
    app = mcp.streamable_http_app(transport_security=security)
    app.add_middleware(MCPAuthMiddleware)
    return app


async def main() -> None:
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("Supervisor API access is unavailable; refusing to start")
    mcp_config = uvicorn.Config(_mcp_asgi(), host="0.0.0.0", port=8765, log_level="warning")
    ui_config = uvicorn.Config(ui_app, host="0.0.0.0", port=8099, log_level="warning")
    await asyncio.gather(uvicorn.Server(mcp_config).serve(), uvicorn.Server(ui_config).serve())


if __name__ == "__main__":
    asyncio.run(main())
