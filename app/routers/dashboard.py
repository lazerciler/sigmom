#!/usr/bin/env python3
# app/routers/dashboard.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")


@router.get("/ui", response_class=HTMLResponse)
async def dashboard_ui(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
