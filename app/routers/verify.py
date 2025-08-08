from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.handlers.order_verification_handler import verify_pending_trades

router = APIRouter()


@router.post("/verify-open-trades")
async def trigger_verification(db: AsyncSession = Depends(get_db)):
    """
    Tüm pending open trades işlemleri kontrol eder.
    """
    await verify_pending_trades(db)
    return {"success": True, "message": "Kontrol işlemi tamamlandı."}
