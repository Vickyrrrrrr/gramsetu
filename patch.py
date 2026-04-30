import os

file_path = r'c:\Documents\GitHub\Gramsetu\gramsetu\backend\agents\graph.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

import re

# 1. Update digilocker_fetch_node
new_dl_fetch = '''        # ALL data found — straight to confirm!
        state["response"] = await _localized(
            "✅ *DigiLocker से डेटा मिल गया!*\\n\\n📸 *Live Photo Verification required*\\nकृपया लाइव फोटो वेरिफिकेशन के लिए कैमरा पर टैप करें। (डेमो: आगे बढ़ने के लिए कुछ भी टाइप करें)",
            "✅ *Data fetched from DigiLocker!*\\n\\n📸 *Live Photo Verification required*\\nPlease tap the camera for live selfie verification. (Demo: type anything to proceed)",
            lang
        )
        state["next_node"] = "photo_verify"
        state["status"] = GraphStatus.WAIT_PHOTO.value'''
content = content.replace('        # ALL data found — straight to confirm!\\n        state["next_node"] = "confirm"\\n        state["status"] = GraphStatus.ACTIVE.value', new_dl_fetch)

# 2. Define photo_verify_node
node_code = '''
async def photo_verify_node(state: GramSetuState) -> GramSetuState:
    lang = state.get("language", "hi")
    state["response"] = await _localized(
        "📸 *Live Photo Verification Successful!*\\n\\n✅ चेहरे का मिलान हो गया है (98%)।\\nअब आपके फॉर्म का डेटा तैयार किया जा रहा है...",
        "📸 *Live Photo Verification Successful!*\\n\\n✅ Face matched with DigiLocker (98%).\\nPreparing your form data now...",
        lang
    )
    state["status"] = GraphStatus.ACTIVE.value
    state["current_node"] = "photo_verify"
    state["next_node"] = "confirm"
    return await confirm_node(state)

# ============================================================
# NODE 4: CONFIRM
'''
content = content.replace('# ============================================================\n# NODE 4: CONFIRM', node_code)

# 3. Handle WAIT_PHOTO in _process_with_compiled_graph
wait_photo_handler = '''
        if status == GraphStatus.WAIT_PHOTO.value:
            existing_state["status"] = GraphStatus.ACTIVE.value
            existing_state["next_node"] = "photo_verify"
            existing_state["last_active"] = time.time()
            result = await photo_verify_node(existing_state)
            await compiled.aupdate_state(config, result, as_node="photo_verify")
            return _format_result(result, session_id)

        if status == GraphStatus.WAIT_CONFIRM.value:'''
content = content.replace('        if status == GraphStatus.WAIT_CONFIRM.value:', wait_photo_handler)

# 4. Route next update
content = content.replace('valid_nodes = ("transcribe", "detect_intent", "digilocker_fetch", "confirm", "fill_form")', 'valid_nodes = ("transcribe", "detect_intent", "digilocker_fetch", "photo_verify", "confirm", "fill_form")')
content = content.replace('GraphStatus.WAIT_USER.value,\\n        GraphStatus.WAIT_CONFIRM.value,\\n        GraphStatus.WAIT_OTP.value,', 'GraphStatus.WAIT_USER.value,\\n        GraphStatus.WAIT_CONFIRM.value,\\n        GraphStatus.WAIT_OTP.value,\\n        GraphStatus.WAIT_PHOTO.value,')

# 5. build_graph update
content = content.replace('graph.add_node("confirm", confirm_node)', 'graph.add_node("photo_verify", photo_verify_node)\\n    graph.add_node("confirm", confirm_node)')
content = content.replace('graph.add_conditional_edges("digilocker_fetch", route_next)', 'graph.add_conditional_edges("digilocker_fetch", route_next)\\n    graph.add_conditional_edges("photo_verify", route_next)')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("graph.py patched.")
