from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from backend.integrations.schemes import discover_schemes
from backend.api.state import _impact

router = APIRouter(tags=["services"])



