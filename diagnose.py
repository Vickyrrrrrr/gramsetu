import socket
import sys
import os

def check_port(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except:
            return False

print("--- GramSetu Diagnostics ---")
print(f"Python: {sys.version}")
print(f"Working Dir: {os.getcwd()}")
print(f"Port 8000 (127.0.0.1): {'OPEN' if check_port('127.0.0.1', 8000) else 'CLOSED'}")
print(f"Port 8000 (localhost): {'OPEN' if check_port('localhost', 8000) else 'CLOSED'}")
print(f"Port 8101 (Browser MCP): {'OPEN' if check_port('127.0.0.1', 8101) else 'CLOSED'}")

# Now let's try to fix the server.py one last time
path = 'server.py'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Change back to 0.0.0.0 for maximum compatibility, but keep MCPs on 127.0.0.1
    content = content.replace('host="127.0.0.1"', 'host="0.0.0.0"')
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched server.py to bind to 0.0.0.0")
