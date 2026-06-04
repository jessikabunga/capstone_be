import random
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from datetime import datetime, timezone

def generate_dummy_ml():
    print("Membuat data dummy ML untuk testing Frontend...")
    db: Session = SessionLocal()
    
    # Ambil semua user yang sudah register di database
    users = db.query(models.Profile).all()
    
    if not users:
        print("Belum ada user di database. Register minimal 1 user dulu via API /register!")
        return

    CTAS = ["Investment", "Apply Credit Card", "Voucher", "Savings", "My Schedule"]
    CATEGORIES = ["Food & Beverage", "E-Wallet", "Transport & Mobility", "Utilities"]

    for user in users:
        # Ngacak user masuk ke cluster 0, 1, 2, atau 3
        dummy_cluster = random.randint(0, 3) 
        dummy_cta = random.choice(CTAS)
        dummy_category = random.choice(CATEGORIES)
        
        msg = f"[TESTING] Halo {user.full_name}, ini adalah insight palsu. Fokus transaksimu ada di {dummy_category}."

        existing = db.query(models.ClusteringResult).filter(models.ClusteringResult.user_id == user.user_id).first()
        
        if existing:
            existing.cluster_id = dummy_cluster
            existing.predicted_cta = dummy_cta
            existing.generated_message = msg
            existing.category_focus = dummy_category
            existing.timestamp = datetime.now(timezone.utc)
        else:
            new_res = models.ClusteringResult(
                user_id=user.user_id,
                cluster_id=dummy_cluster,
                predicted_cta=dummy_cta,
                generated_message=msg,
                category_focus=dummy_category,
                recommendation_confidence=0.99,
                timestamp=datetime.now(timezone.utc)
            )
            db.add(new_res)
            
    db.commit()
    db.close()
    print(f"Sukses! Berhasil menyuntikkan data ML palsu ke {len(users)} user.")
    print("Sekarang Frontend bisa test endpoint GET /recommendation dan melihat data bervariasi!")

if __name__ == "__main__":
    generate_dummy_ml()