from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models
import schemas

# Otomatis membuat tabel jika belum ada (meskipun kamu sudah buat via SQL)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Banking API Capstone")

# ==========================================
# DICTIONARY PROMO (Berdasarkan Flowchart PM)
# ==========================================
# Ini simulasi hasil dari PM. Kita anggap Cluster ID dari ML adalah:
# 1 = Mahasiswa
# 2 = Young Professional
# 3 = Established Professional
# 4 = Freelancer

PROMO_CATALOG = {
    1: {"title": "Diskon 50% QRIS Kopi Kenangan & Mie Gacoan!", "type": "Promo #1"},
    2: {"title": "Cashback Top Up E-Wallet s/d Rp 50.000", "type": "Promo #2"},
    3: {"title": "Penawaran Spesial: Limit Kartu Kredit s/d 50 Juta", "type": "Promo #3"},
    4: {"title": "Bebas Biaya Transfer Antar Bank Selama Sebulan!", "type": "Promo #1"},
    "general": {"title": "Waspada Penipuan! Jaga Kerahasiaan PIN Anda", "type": "Non-Promo"}
}

@app.get("/")
def read_root():
    return {"message": "Backend API is Running!"}

# ==========================================
# ENDPOINT JAGOAN: GET /recommendation/{user_id}
# ==========================================
@app.get("/recommendation/{user_id}", response_model=schemas.PromoResponse)
def get_recommendation(user_id: str, db: Session = Depends(get_db)):
    
    # 1. Cari user di database (dim_profile)
    user = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    # 2. Cek Consent (Sesuai Diagram Kamu)
    if user.consent_personalization == False:
        # Jika false, kirim promo umum/statis
        return schemas.PromoResponse(
            user_id=user.user_id,
            message="User opted out of personalization",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"]
        )
    
    # 3. Jika Consent True, ambil dari hasil ML (clustering_results)
    ml_result = db.query(models.ClusteringResult).filter(models.ClusteringResult.user_id == user_id).first()
    
    if not ml_result or ml_result.cluster_id not in PROMO_CATALOG:
        # Jika data ML belum ada, kirim promo default
        return schemas.PromoResponse(
            user_id=user.user_id,
            message="Data ML belum siap, mengirim promo default",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"]
        )

    # 4. Result Mapping (Cocokkan Cluster ID dengan Promo)
    selected_promo = PROMO_CATALOG[ml_result.cluster_id]
    
    return schemas.PromoResponse(
        user_id=user.user_id,
        message=f"Success getting promo for {user.occupation}",
        promo_title=selected_promo["title"],
        promo_type=selected_promo["type"]
    )