import re
import os
import shutil

def replace_in_file(path, old, new):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# Update app.py
app_py = 'backend/api/app.py'
replace_in_file(app_py, 'from backend.orchestrator.flow import', 'from backend.agents.pipeline import')
replace_in_file(app_py, 'from backend.orchestrator.models import', 'from backend.agents.schema import')
replace_in_file(app_py, 'from backend.integrations.security import', 'from backend.security import')
replace_in_file(app_py, 'from backend.integrations.schemes import', 'from backend.schemes import')

# Update test_package_structure.py
test_py = 'tests/test_package_structure.py'
replace_in_file(test_py, 'from backend.orchestrator.flow import', 'from backend.agents.pipeline import')
replace_in_file(test_py, 'from backend.orchestrator.models import', 'from backend.agents.schema import')
replace_in_file(test_py, 'from backend.integrations.security import', 'from backend.security import')
replace_in_file(test_py, 'from backend.integrations.schemes import', 'from backend.schemes import')
replace_in_file(test_py, 'from backend.integrations.llm import chat', 'from backend.llm_client import _sarvam_respond as chat')

# Delete facade directories
if os.path.exists('backend/orchestrator'):
    shutil.rmtree('backend/orchestrator')
if os.path.exists('backend/integrations'):
    shutil.rmtree('backend/integrations')

print("Refactored imports and removed facade directories.")
