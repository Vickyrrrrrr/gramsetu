"""
============================================
schemas.py — Form Schemas (Pydantic Models)
============================================
Defines the structure of government forms with
field definitions, validation rules, and required documents.
"""

from pydantic import BaseModel
from typing import Optional
import json
import os

# ---- Form Field Schema ----

class FormField(BaseModel):
    """A single field in a government form."""
    key: str                           # Field identifier
    label: str                         # English label
    label_hi: str                      # Hindi label
    field_type: str = "text"           # text, number, date, select, aadhaar, pan
    required: bool = True
    options: list[str] = []            # For select-type fields
    ask_prompt_en: str = ""            # What to ask in English
    ask_prompt_hi: str = ""            # What to ask in Hindi


class FormSchema(BaseModel):
    """Complete schema for a government form."""
    form_id: str
    name: str
    name_hi: str
    description: str
    description_hi: str
    fields: list[FormField]
    required_documents: list[str] = []


# ---- Load Form Schemas from JSON ----

FORMS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "forms")


def load_form_schema(form_type: str) -> Optional[FormSchema]:
    """Load a form schema from the JSON file."""
    filepath = os.path.join(FORMS_DIR, f"{form_type}.json")
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    fields = [FormField(**field) for field in data.get("fields", [])]
    return FormSchema(
        form_id=data["form_id"],
        name=data["name"],
        name_hi=data["name_hi"],
        description=data["description"],
        description_hi=data["description_hi"],
        fields=fields,
        required_documents=data.get("required_documents", []),
    )


def get_available_forms() -> list[dict]:
    """List all available form schemas."""
    forms = []
    if os.path.exists(FORMS_DIR):
        for filename in os.listdir(FORMS_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(FORMS_DIR, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                forms.append({
                    "form_id": data.get("form_id"),
                    "name": data.get("name"),
                    "name_hi": data.get("name_hi"),
                    "description": data.get("description"),
                })
    return forms


def get_next_missing_field(form_type: str, filled_data: dict) -> Optional[FormField]:
    """
    Find the next required field that hasn't been filled yet.
    Used to drive the conversational flow — ask one field at a time.
    """
    schema = load_form_schema(form_type)
    if not schema:
        return None
    
    for field in schema.fields:
        if field.required and field.key not in filled_data:
            return field
    
    return None  # All required fields are filled
