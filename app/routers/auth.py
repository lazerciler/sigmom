#!/usr/bin/env python3
# app/routes/auth.py
# Python 3.9
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/auth/logout")
async def logout(request: Request):
    """
    Kullanıcı oturumunu sonlandırır ve ana sayfaya yönlendirir.
    """
    request.session.clear()
    return RedirectResponse(url="/")
