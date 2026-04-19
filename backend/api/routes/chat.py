import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from backend.storage import db
from backend.orchestrator.flow import process_message as v3_process_message
from backend.orchestrator.models import GraphStatus
from backend.integrations.security import api_limiter, sanitize_input, validate_otp_input
from backend.services.session_store import get_chat_session, save_chat_session, save_completed_session
from backend.api.state import _user_sessions, _completed_forms, _impact

router = APIRouter(tags=["chat"])


