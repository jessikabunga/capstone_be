from pydantic import BaseModel

# Skema untuk respons API Recommendation
class PromoResponse(BaseModel):
    user_id: str
    message: str
    promo_title: str
    promo_type: str # Misal: "Promo #1", "Promo #2", atau "General"

    class Config:
        from_attributes = True