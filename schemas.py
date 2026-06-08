from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime

class PromoResponse(BaseModel):
    user_id: int
    message: str
    promo_title: str
    promo_type: str
    generated_message: Optional[str] = None
    predicted_cta: Optional[str] = None
    cta_url: Optional[str] = None
    trigger_reason: Optional[str] = None
    category_focus: Optional[str] = None

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
    interaction_type: Optional[str] = None

    class Config:
        from_attributes = True

class TransactionCreate(BaseModel):
    category: str
    merchant_name: str
    transaction_method: str
    amount: Decimal
    pin: str
    notes: Optional[str] = None
    recipient_bank: Optional[str] = None
    recipient_account: Optional[str] = None

    class Config:
        from_attributes = True

class SavedContactCreate(BaseModel):
    name: str
    account_number: str
    bank_name: Optional[str] = None
    category: str

class SavedContactResponse(BaseModel):
    id: int
    user_id: int
    name: str
    account_number: str
    bank_name: Optional[str] = None
    category: str

    class Config:
        from_attributes = True
