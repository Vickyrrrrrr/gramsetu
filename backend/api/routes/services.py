from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any

from backend.persistent_state import get_state, set_state
from backend.security import encrypt_pii, decrypt_pii

router = APIRouter(tags=["services"])

class VaultItem(BaseModel):
    id: str
    label: str
    value: str

class VaultPayload(BaseModel):
    items: List[VaultItem]

@router.get("/api/vault/{user_id}")
async def get_vault(user_id: str):
    """Retrieve user's encrypted vault data."""
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    
    data = get_state("vault", user_id)
    if not data:
        return {"items": []}
    
    # Decrypt the values
    items = []
    for item in data.get("items", []):
        try:
            decrypted_val = decrypt_pii(item["value"])
            items.append({
                "id": item["id"],
                "label": item["label"],
                "value": decrypted_val
            })
        except Exception:
            # If decryption fails, skip or return empty
            pass
            
    return {"items": items}

@router.post("/api/vault/{user_id}")
async def save_vault(user_id: str, payload: VaultPayload):
    """Save encrypted user data to the vault."""
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
        
    encrypted_items = []
    for item in payload.items:
        encrypted_items.append({
            "id": item.id,
            "label": item.label,
            "value": encrypt_pii(item.value)
        })
        
    success = set_state("vault", user_id, {"items": encrypted_items})
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save to vault")
        
    return {"status": "success"}



