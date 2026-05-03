import os
path = 'server.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Force 0.0.0.0 for WSL compatibility
content = content.replace('host="127.0.0.1"', 'host="0.0.0.0"')
content = content.replace("host='127.0.0.1'", "host='0.0.0.0'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully patched server.py for WSL compatibility")
