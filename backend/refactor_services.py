import os
import shutil

# Move session_store.py
shutil.move('backend/services/session_store.py', 'backend/session_store.py')

# Update app.py
app_py = 'backend/api/app.py'
with open(app_py, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('from backend.services.session_store import', 'from backend.session_store import')

with open(app_py, 'w', encoding='utf-8') as f:
    f.write(content)

# Delete backend/services
shutil.rmtree('backend/services')

print("Moved session_store and removed backend/services")
