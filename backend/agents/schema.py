"""
============================================================
schema.py — Pydantic-AI Models for GramSetu v3
============================================================
Strict schema validation for every government form.
The LangGraph MUST validate all user input against these models
before the agent proceeds to the next node.

Schemas:
  - GramSetuState:   TypedDict for LangGraph state
  - RationCard:      Fair Price Shop / BPL ration card
  - PensionScheme:   Old Age / Widow / Disability pension
  - Identity:        PAN Card / Voter ID application
  - Address:         Reusable address sub-model
  - BankAccount:     Reusable bank details sub-model
"""

import re
from datetime import date, datetime
from typing import Optional, Literal, Annotated
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import TypedDict


# ============================================================
# LangGraph State Schema (TypedDict — required by LangGraph)
# ============================================================

class GraphStatus(str, Enum):
    """Current status of the LangGraph execution."""
    ACTIVE = "active"
    WAIT_OTP = "wait_otp"
    WAIT_CONFIRM = "wait_confirm"
    WAIT_USER = "wait_user"
    COMPLETED = "completed"
    ERROR = "error"


class GramSetuState(TypedDict, total=False):
    """
    Shared state that flows through all LangGraph nodes.
    This is the single source of truth during a session.

    PII fields (aadhaar, phone, etc.) live ONLY here —
    they are NEVER written to logs or API responses.
    """
    # ── Session Identifiers ──────────────────────────────────
    session_id: str
    user_id: str
    user_phone: str

    # ── Input ────────────────────────────────────────────────
    raw_message: str
    message_type: str           # "text" | "voice" | "otp"
    language: str               # "hi" | "en" | "hinglish"
    transcribed_text: str       # ASR output (for voice)

    # ── Form Context ─────────────────────────────────────────
    form_type: str              # "ration_card" | "pension" | "identity"
    form_data: dict             # Extracted field values (may contain PII)
    confidence_scores: dict     # Confidence per field (0.0–1.0)
    validation_errors: list     # List of field validation errors
    missing_fields: list        # Fields still needed from user
    self_critique: str          # Agent's self-critique of extraction

    # ── Graph Control ────────────────────────────────────────
    status: str                 # GraphStatus value
    current_node: str           # Active node name
    next_node: str              # Where to route next
    response: str               # Message to send to user
    confirmation_summary: str   # Human-readable form summary
    otp_value: str              # OTP received from user (temp only)

    # ── Browser State ────────────────────────────────────────
    browser_launched: bool
    portal_url: str
    screenshot_b64: str         # Latest screenshot for VLM
    otp_field_position: dict    # {"x": int, "y": int}

    # ── Timing ───────────────────────────────────────────────
    last_active: float          # Unix timestamp of last user message

    # ── Audit ────────────────────────────────────────────────
    audit_entries: list         # Reasoning trail for this session
    pii_accessed: list          # Which PII fields were used


# ============================================================
# Reusable Sub-Models
# ============================================================

class Address(BaseModel):
    """Indian address with mandatory PIN code."""
    line1: str = Field(..., min_length=5, max_length=200, description="House/Flat/Village")
    line2: Optional[str] = Field(None, max_length=200, description="Street/Locality")
    district: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=30)
    pincode: str = Field(..., pattern=r"^[1-9]\d{5}$", description="6-digit PIN code")

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: str) -> str:
        clean = re.sub(r"\s", "", v)
        if not re.match(r"^[1-9]\d{5}$", clean):
            raise ValueError("PIN code must be 6 digits, first digit 1-9")
        return clean


class BankAccount(BaseModel):
    """Indian bank account details for direct benefit transfer."""
    account_holder_name: str = Field(..., min_length=2, max_length=100)
    account_number: str = Field(..., min_length=8, max_length=18)
    ifsc_code: str = Field(..., pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    bank_name: str = Field(..., min_length=2, max_length=100)
    branch_name: Optional[str] = Field(None, max_length=100)

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: str) -> str:
        v = v.upper().strip()
        if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", v):
            raise ValueError("IFSC format: 4 letters + 0 + 6 alphanumeric (e.g., SBIN0001234)")
        return v


# ============================================================
# Schema 1: Ration Card Application
# ============================================================

class RationCard(BaseModel):
    """
    Fair Price Shop / BPL Ration Card application.
    Required for subsidized food grain distribution.
    """
    applicant_name: str = Field(
        ..., min_length=2, max_length=100,
        description="Full name as per Aadhaar"
    )
    aadhaar_number: str = Field(
        ..., description="12-digit Aadhaar number"
    )
    date_of_birth: date = Field(
        ..., description="Date of birth (YYYY-MM-DD)"
    )
    gender: Literal["male", "female", "other"] = Field(
        ..., description="Gender"
    )
    family_head_name: str = Field(
        ..., min_length=2, max_length=100,
        description="Head of family name"
    )
    family_members: int = Field(
        ..., ge=1, le=20,
        description="Total number of family members"
    )
    annual_income: float = Field(
        ..., ge=0, le=10_000_000,
        description="Annual household income in INR"
    )
    category: Literal["APL", "BPL", "AAY"] = Field(
        ..., description="APL (Above Poverty Line), BPL (Below), AAY (Antyodaya)"
    )
    mobile_number: str = Field(
        ..., description="10-digit mobile number"
    )
    address: Address
    existing_ration_card: Optional[str] = Field(
        None, description="Existing ration card number (if any)"
    )

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be exactly 12 digits")
        if clean[0] in "01":
            raise ValueError("Aadhaar cannot start with 0 or 1")
        # Verhoeff checksum
        d = [
            [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],
            [2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
            [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
            [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],
            [8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]
        ]
        p = [
            [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],
            [5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
            [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
            [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]
        ]
        c = 0
        for i, digit in enumerate(int(x) for x in reversed(clean)):
            c = d[c][p[i % 8][digit]]
        if c != 0:
            raise ValueError("Aadhaar checksum (Verhoeff) failed")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting with 6-9")
        return clean

    @field_validator("date_of_birth")
    @classmethod
    def validate_age(cls, v: date) -> date:
        age = (date.today() - v).days // 365
        if age < 18:
            raise ValueError("Applicant must be at least 18 years old")
        if age > 150:
            raise ValueError("Invalid date of birth")
        return v


# ============================================================
# Schema 2: Pension Scheme Application
# ============================================================

class PensionScheme(BaseModel):
    """
    Old Age / Widow / Disability pension application.
    Under NSAP (National Social Assistance Programme).
    """
    applicant_name: str = Field(
        ..., min_length=2, max_length=100,
        description="Full name as per Aadhaar"
    )
    aadhaar_number: str = Field(
        ..., description="12-digit Aadhaar number"
    )
    date_of_birth: date = Field(
        ..., description="Date of birth"
    )
    pension_type: Literal["old_age", "widow", "disability"] = Field(
        ..., description="Type of pension"
    )
    gender: Literal["male", "female", "other"]
    mobile_number: str = Field(
        ..., description="10-digit mobile number"
    )
    bank_account: BankAccount
    address: Address
    annual_income: float = Field(
        ..., ge=0, le=10_000_000,
        description="Annual income in INR"
    )
    bpl_card_number: Optional[str] = Field(
        None, description="BPL card number if applicable"
    )
    disability_certificate: Optional[str] = Field(
        None, description="Disability certificate number (for disability pension)"
    )
    spouse_death_certificate: Optional[str] = Field(
        None, description="Spouse death certificate (for widow pension)"
    )

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be exactly 12 digits")
        if clean[0] in "01":
            raise ValueError("Aadhaar cannot start with 0 or 1")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting with 6-9")
        return clean

    @model_validator(mode="after")
    def validate_pension_eligibility(self):
        age = (date.today() - self.date_of_birth).days // 365
        if self.pension_type == "old_age" and age < 60:
            raise ValueError("Old age pension requires age >= 60")
        if self.pension_type == "widow" and not self.spouse_death_certificate:
            raise ValueError("Widow pension requires spouse death certificate")
        if self.pension_type == "disability" and not self.disability_certificate:
            raise ValueError("Disability pension requires disability certificate")
        return self


# ============================================================
# Schema 3: Identity Document Application
# ============================================================

class Identity(BaseModel):
    """
    PAN Card (Form 49A) or Voter ID application.
    """
    full_name: str = Field(
        ..., min_length=2, max_length=100,
        description="Full name as per Aadhaar"
    )
    date_of_birth: date = Field(
        ..., description="Date of birth"
    )
    document_type: Literal["pan_card", "voter_id"] = Field(
        ..., description="Type of identity document"
    )
    gender: Literal["male", "female", "other"]
    father_name: str = Field(
        ..., min_length=2, max_length=100,
        description="Father's full name"
    )
    aadhaar_number: str = Field(
        ..., description="12-digit Aadhaar number for verification"
    )
    mobile_number: str = Field(
        ..., description="10-digit mobile number"
    )
    email: Optional[str] = Field(
        None, description="Email address (optional)"
    )
    address: Address
    photo_url: Optional[str] = Field(
        None, description="Passport-size photo URL"
    )
    signature_url: Optional[str] = Field(
        None, description="Scanned signature URL"
    )

    # PAN-specific fields
    pan_category: Optional[Literal[
        "individual", "company", "firm", "trust", "government"
    ]] = Field(None, description="PAN holder category (for PAN card)")
    source_of_income: Optional[Literal[
        "salary", "business", "no_income", "capital_gains", "other"
    ]] = Field(None, description="Primary source of income")

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be exactly 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting with 6-9")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("Invalid email format")
        return v

    @model_validator(mode="after")
    def validate_pan_specific(self):
        if self.document_type == "pan_card" and not self.pan_category:
            self.pan_category = "individual"
        return self


# ============================================================
# Schema 4: Ayushman Bharat (PMJAY) Application
# ============================================================

class AyushmanBharat(BaseModel):
    """Health insurance of ₹5 lakh/year under PM-JAY."""
    applicant_name: str = Field(..., min_length=2, max_length=100)
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    mobile_number: str
    annual_income: float = Field(..., ge=0, le=500000, description="Must be ≤ ₹5 lakh")
    family_members: int = Field(..., ge=1, le=20)
    bpl_card_number: Optional[str] = None
    caste: Optional[Literal["general", "obc", "sc", "st"]] = None
    address: Address
    bank_account: BankAccount

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting 6-9")
        return clean


# ============================================================
# Schema 5: PM-KISAN Application
# ============================================================

class PMKisan(BaseModel):
    """PM-KISAN: ₹6,000/year direct income support to farmers."""
    applicant_name: str = Field(..., min_length=2, max_length=100)
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    mobile_number: str
    land_holding_acres: float = Field(..., ge=0.0, description="Land in acres")
    land_record_number: Optional[str] = None
    annual_income: float = Field(..., ge=0, le=200000)
    address: Address
    bank_account: BankAccount
    state_code: Optional[str] = Field(None, max_length=3, description="State code e.g. UP, MH")

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting 6-9")
        return clean


# ============================================================
# Schema 6: MNREGA Job Card Application
# ============================================================

class MNREGAJobCard(BaseModel):
    """MNREGA: 100 days of guaranteed rural employment."""
    applicant_name: str = Field(..., min_length=2, max_length=100)
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    mobile_number: str
    household_head_name: str = Field(..., min_length=2, max_length=100)
    family_members: int = Field(..., ge=1, le=20)
    sc_st_category: bool = Field(False, description="Is applicant SC/ST?")
    address: Address
    bank_account: BankAccount

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting 6-9")
        return clean


# ============================================================
# Schema 7: Birth Certificate Application
# ============================================================

class BirthCertificate(BaseModel):
    """Birth certificate registration / issuance."""
    child_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date
    place_of_birth: str = Field(..., min_length=2, max_length=200)
    gender: Literal["male", "female", "other"]
    father_name: str = Field(..., min_length=2, max_length=100)
    mother_name: str = Field(..., min_length=2, max_length=100)
    father_aadhaar: Optional[str] = None
    mother_aadhaar: Optional[str] = None
    hospital_name: Optional[str] = Field(None, max_length=200)
    mobile_number: str
    address: Address


# ============================================================
# Schema 8: Caste Certificate Application
# ============================================================

class CasteCertificate(BaseModel):
    """SC/ST/OBC caste certificate for government benefits."""
    applicant_name: str = Field(..., min_length=2, max_length=100)
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    caste: Literal["sc", "st", "obc"]
    sub_caste: Optional[str] = Field(None, max_length=100)
    father_name: str = Field(..., min_length=2, max_length=100)
    mobile_number: str
    address: Address
    annual_income: Optional[float] = Field(None, ge=0)

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting 6-9")
        return clean


# ============================================================
# Schema 9: Kisan Credit Card (KCC)
# ============================================================

class KisanCreditCard(BaseModel):
    """Kisan Credit Card: subsidised credit for farmers."""
    applicant_name: str = Field(..., min_length=2, max_length=100)
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    mobile_number: str
    land_holding_acres: float = Field(..., ge=0.1)
    land_record_number: str = Field(..., min_length=3)
    crop_type: str = Field(..., description="Primary crop grown e.g. wheat, rice")
    loan_amount_required: float = Field(..., ge=5000, le=3000000)
    annual_income: float = Field(..., ge=0)
    address: Address
    bank_account: BankAccount

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting 6-9")
        return clean


# ============================================================
# Schema 10: Jan Dhan Account (PMJDY)
# ============================================================

class JanDhanAccount(BaseModel):
    """PM Jan Dhan Yojana: zero-balance bank account."""
    applicant_name: str = Field(..., min_length=2, max_length=100)
    aadhaar_number: str = Field(..., description="12-digit Aadhaar number")
    date_of_birth: date
    gender: Literal["male", "female", "other"]
    mobile_number: str
    occupation: Literal[
        "farmer", "labourer", "student", "housewife",
        "self_employed", "unemployed", "other"
    ]
    annual_income: Optional[float] = Field(None, ge=0)
    nominee_name: Optional[str] = Field(None, max_length=100)
    nominee_relationship: Optional[str] = Field(None, max_length=50)
    address: Address

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit() or len(clean) != 12:
            raise ValueError("Aadhaar must be 12 digits")
        return clean

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\+]", "", v)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Mobile must be 10 digits starting 6-9")
        return clean


# ============================================================
# Schema Registry — Maps form_type to model class
# Add any new form: just add its Pydantic model above and register here.
# The entire LangGraph pipeline (voice, validation, DigiLocker, fill)
# will work automatically for the new form type.
# ============================================================

SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    # Government welfare
    "ration_card": RationCard,
    "pension": PensionScheme,
    "ayushman_bharat": AyushmanBharat,
    "mnrega": MNREGAJobCard,
    # Identity & credentials
    "identity": Identity,
    "pan_card": Identity,
    "voter_id": Identity,
    "caste_certificate": CasteCertificate,
    "birth_certificate": BirthCertificate,
    # Agriculture & credit
    "pm_kisan": PMKisan,
    "kisan_credit_card": KisanCreditCard,
    # Financial inclusion
    "jan_dhan": JanDhanAccount,
}


def get_schema_for_form(form_type: str) -> Optional[type[BaseModel]]:
    """Get the Pydantic model class for a given form type."""
    return SCHEMA_REGISTRY.get(form_type)


def get_required_fields(form_type: str) -> list[str]:
    """Get the list of required fields for a form type."""
    schema = SCHEMA_REGISTRY.get(form_type)
    if not schema:
        return []

    required = []
    for name, field_info in schema.model_fields.items():
        if field_info.is_required():
            required.append(name)
    return required


def validate_partial_form(form_type: str, data: dict) -> dict:
    """
    Validate partial form data, returning per-field results.

    Returns:
        {
            "valid_fields": {"name": "Ram", ...},
            "errors": {"aadhaar_number": "Must be 12 digits", ...},
            "missing": ["address", "bank_account", ...]
        }
    """
    schema = SCHEMA_REGISTRY.get(form_type)
    if not schema:
        return {"valid_fields": {}, "errors": {"_form": "Unknown form type"}, "missing": []}

    valid_fields = {}
    errors = {}

    # Validate each provided field individually using Pydantic's own validators
    for field_name, value in data.items():
        if field_name not in schema.model_fields:
            continue

        try:
            # Build a minimal dict and attempt to validate just this field
            # by constructing a partial model with model_validate
            # For complex nested types (Address, BankAccount), accept as-is
            field_info = schema.model_fields[field_name]
            annotation = field_info.annotation

            # Check if it's a complex nested model
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                if isinstance(value, dict):
                    annotation.model_validate(value)
                valid_fields[field_name] = value
            else:
                # For simple types, try to run validators via a single-field dict
                # Use model_validate with partial data — Pydantic will run field validators
                try:
                    # Create minimal valid-ish data to trigger field validator
                    test_data = {field_name: value}
                    # Use model_construct to skip required fields, then manually call validator
                    obj = schema.model_construct(**test_data)
                    # If we got here without error, the value is structurally ok
                    # But we also need to run field validators explicitly
                    # Re-validate by checking field-specific patterns
                    validated_value = value
                    if field_name in ("aadhaar_number",) and hasattr(schema, "validate_aadhaar"):
                        validated_value = schema.validate_aadhaar(value)
                    elif field_name in ("mobile_number",) and hasattr(schema, "validate_mobile"):
                        validated_value = schema.validate_mobile(value)
                    elif field_name == "email" and hasattr(schema, "validate_email"):
                        validated_value = schema.validate_email(value)
                    elif field_name == "date_of_birth" and hasattr(schema, "validate_age"):
                        validated_value = schema.validate_age(value)
                    valid_fields[field_name] = validated_value
                except (ValueError, TypeError) as e:
                    errors[field_name] = str(e)
                    continue

        except (ValueError, TypeError) as e:
            errors[field_name] = str(e)

    # Find missing required fields
    required = get_required_fields(form_type)
    missing = [f for f in required if f not in data and f not in errors]

    return {
        "valid_fields": valid_fields,
        "errors": errors,
        "missing": missing,
    }
