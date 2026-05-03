import os
import base64
import requests
import json
from typing import Dict, Optional

def _image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

async def scan_document_with_vlm(image_path: str, form_type: str) -> Dict:
    """
    Uses NVIDIA Llama-3.2-Vision to extract form data from a document image.
    """
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        return {"error": "NVIDIA_API_KEY not found"}

    invoke_url = "https://ai.api.nvidia.com/v1/gr/meta/llama-3.2-11b-vision-instruct/chat/completions"
    
    base64_image = _image_to_base64(image_path)
    
    prompt = f"""You are a government document expert. Extract all possible user information from this document for a {form_type} application.
    Return ONLY valid JSON with 'extracted_data' and 'confidence_scores'.
    If it's an Aadhaar card, extract: full_name, aadhaar_number, dob, gender, address.
    If it's a PAN card, extract: full_name, pan_number, dob.
    Be precise. Return NO other text."""

    payload = {
        "model": "meta/llama-3.2-11b-vision-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.2
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    try:
        response = requests.post(invoke_url, headers=headers, json=payload)
        res_json = response.json()
        content = res_json['choices'][0]['message']['content']
        
        # Clean the JSON output
        import re
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {"extracted_data": {}}
    except Exception as e:
        print(f"[Vision] Extraction failed: {e}")
        return {"extracted_data": {}, "error": str(e)}
