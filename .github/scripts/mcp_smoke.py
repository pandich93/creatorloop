"""Start an MCP stdio server, initialize it and check that the tools are listed.

python .github/scripts/mcp_smoke.py 33 docker run -i --rm creatorloop
"""

import json
import subprocess
import sys

expected, cmd = int(sys.argv[1]), sys.argv[2:]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def request(id_: int, method: str, params: dict | None = None) -> dict:
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    for line in proc.stdout:  # skip server notifications
        msg = json.loads(line)
        if msg.get("id") == id_:
            return msg["result"]
    sys.exit(f"server exited before answering {method}")


info = request(
    1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}}
)
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
tools = request(2, "tools/list")["tools"]
proc.stdin.close()
proc.wait(timeout=30)
print(f"{info['serverInfo']['name']} {info['serverInfo']['version']}: {len(tools)} tools")
if len(tools) < expected:
    sys.exit(f"expected at least {expected} tools")
