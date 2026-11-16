# Separate TEST candidate, no original Worker replacement.
# Version tag is NOT digest pinned; verify before production.
FROM ghcr.io/moryoav/codex-cli-worker:0.1.82
COPY apply_worker_patch.py controlled_bridge_mcp.py /opt/ha-bridge-patch/
RUN set -eu; \
    mkdir -p /tmp/ha-bridge-upstream; \
    git -C /tmp/ha-bridge-upstream init -q; \
    git -C /tmp/ha-bridge-upstream remote add origin https://github.com/moryoav/home-assistant-codex.git; \
    git -C /tmp/ha-bridge-upstream fetch -q --depth=1 origin ce05342ec6e9b8b18df8c7884f5cad4eb72f60a3; \
    git -C /tmp/ha-bridge-upstream checkout -q --detach FETCH_HEAD; \
    python3 /opt/ha-bridge-patch/apply_worker_patch.py /tmp/ha-bridge-upstream; \
    cp /tmp/ha-bridge-upstream/codex-cli-worker/server.py /server.py; \
    cp /tmp/ha-bridge-upstream/codex-cli-worker/controlled_bridge_mcp.py /controlled_bridge_mcp.py; \
    python3 -m py_compile /server.py /controlled_bridge_mcp.py; \
    rm -rf /tmp/ha-bridge-upstream /opt/ha-bridge-patch
# Original /run.sh, AppArmor, dependencies and browser stack remain untouched.
