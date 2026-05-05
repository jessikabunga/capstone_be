from pydantic import BaseModel

# Skema untuk respons API Recommendation
class PromoResponse(BaseModel):
    user_id: int
    message: str
    promo_title: str
    promo_type: str

    class Config:
        from_attributes = True