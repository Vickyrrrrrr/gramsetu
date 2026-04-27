import sys

path = 'c:/Documents/GitHub/Gramsetu/gramsetu/webapp/app/app/page.tsx'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We want to replace the block starting at 'useEffect(() => {' (around line 925)
# and ending at '}, [userId])' (around line 951)

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if 'Browser preview WebSocket — always-on with auto-reconnect' in line:
        start_idx = i + 1 # useEffect is on next line
        break

if start_idx != -1:
    for i in range(start_idx, len(lines)):
        if '}, [userId])' in lines[i]:
            end_idx = i
            break

if start_idx != -1 and end_idx != -1:
    new_block = [
        "  useEffect(() => {\n",
        "    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'\n",
        "    let ws: WebSocket | null = null\n",
        "    let reconnectTimer: ReturnType<typeof setTimeout> | null = null\n",
        "    let alive = true\n",
        "\n",
        "    const connect = () => {\n",
        "      if (!alive) return\n",
        "      try {\n",
        "        const wsHost = `${window.location.hostname}:8000`\n",
        "        ws = new WebSocket(`${wsProto}://${wsHost}/ws/browser/${userId}`)\n",
        "      } catch { return }\n",
        "      wsRef.current = ws\n",
        "\n",
        "      ws.onmessage = (ev) => {\n",
        "        try {\n",
        "          const msg = JSON.parse(ev.data)\n",
        "          if (msg.type === 'browser_frame') {\n",
        "            setBrowserFrame(msg.screenshot)\n",
        "            setBrowserStep(msg.step || '')\n",
        "            setBrowserProgress(msg.progress ?? 0)\n",
        "          }\n",
        "        } catch { /* ignore non-json */ }\n",
        "      }\n",
        "\n",
        "      ws.onclose = () => {\n",
        "        wsRef.current = null\n",
        "        if (alive) reconnectTimer = setTimeout(connect, 3000)\n",
        "      }\n",
        "\n",
        "      ws.onerror = () => { ws?.close() }\n",
        "    }\n",
        "\n",
        "    connect()\n",
        "\n",
        "    return () => {\n",
        "      alive = false\n",
        "      if (reconnectTimer) clearTimeout(reconnectTimer)\n",
        "      ws?.close()\n",
        "      wsRef.current = null\n",
        "    }\n",
        "  }, [userId])\n"
    ]
    
    lines[start_idx:end_idx+1] = new_block
    
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Successfully fixed page.tsx")
else:
    print(f"Could not find markers: start_idx={start_idx}, end_idx={end_idx}")
    sys.exit(1)
