import os
path = 'server.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix binding
content = content.replace('host="0.0.0.0"', 'host="127.0.0.1"')

# Fix subprocess spawning for Windows stability
old_spawn = """def _spawn_mcp(name: str, port: int):
    \"\"\"Spawn an MCP server as a separate background process.\"\"\"
    print(f"[System] Spawning {name} MCP on 127.0.0.1:{port}...")
    cmd = [
        sys.executable, \"-c\",
        f\"from backend.mcp_servers.{name.lower()}_mcp import mcp; \"
        f\"import uvicorn; \"
        f\"uvicorn.run(mcp.app, host='127.0.0.1', port={port}, log_level='error')\"
    ]
    try:
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[System] Failed to spawn {name}: {e}")
        return None"""

new_spawn = """def _spawn_mcp(name: str, port: int):
    \"\"\"Spawn an MCP server as a separate background process.\"\"\"
    print(f"[System] Spawning {name} MCP on 127.0.0.1:{port}...")
    # Use shell=True and a single string for Windows stability
    inner_cmd = f\"from backend.mcp_servers.{name.lower()}_mcp import mcp; import uvicorn; uvicorn.run(mcp.app, host='127.0.0.1', port={port}, log_level='error')\"
    cmd = f'\"{sys.executable}\" -c \"{inner_cmd}\"'
    try:
        return subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[System] Failed to spawn {name}: {e}")
        return None"""

if old_spawn in content:
    content = content.replace(old_spawn, new_spawn)
else:
    print("Warning: Could not find old_spawn block exactly. Trying fuzzy match.")
    # Fallback to a simpler replacement if whitespace differs
    import re
    content = re.sub(r'def _spawn_mcp.*?return None', new_spawn, content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully patched server.py")
