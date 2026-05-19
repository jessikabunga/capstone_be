from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime

# Skema untuk respons API Recommendation
class PromoResponse(BaseModel):
    user_id: int
    message: str
    promo_title: str
    promo_type: str

    class Config:
        from_attributes = True

class TransactionResponse(BaseModel):
    trx_id: int
    amount: Decimal
    merchant_name: str
    timestamp: datetime
    
    class Config:
        from_attributes = True

class InteractionCreate(BaseModel):
    user_id: Optional[int] = None
    session_id: str
    feature_accessed: str
    action: str

    class Config:
        from_attributes = True