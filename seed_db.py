import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from passlib.context import CryptContext
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

models.Base.metadata.create_all(bind=engine)
db: Session = SessionLocal()

# Profile
df_profile = pd.read_csv('dim_profile.csv')
print(f"Seeding {len(df_profile)} users...")

for _, row in df_profile.iterrows():
    existing = db.query(models.Profile).filter(
        models.Profile.user_id == int(row['user_id'])
    ).first()
    if existing:
        continue

    db.add(models.Profile(
        user_id              = int(row['user_id']),
        username             = str(row['username']),
        password_hash        = pwd_context.hash("Demo1234!"),
        pin_hash             = pwd_context.hash("123456"),
        account_number       = str(row.get('account_number', f"ACC{row['user_id']}")),
        full_name            = str(row['full_name']),
        email_address        = str(row['email_address']),
        phone_number         = str(row['phone_number']),
        city                 = str(row['city']),
        province             = str(row['province']),
        age                  = int(row['age']),
        occupation           = str(row['occupation']),
        monthly_income       = float(row['monthly_income']),
        account_balance      = float(row['account_balance']),
        consent_personalization = bool(row['consent_personalization']),
        segment_ground_truth = str(row['segment_ground_truth']),
        created_at           = datetime.now()
    ))

db.commit()
print("✓ Profile selesai")

# Transaction
df_trx = pd.read_csv('fact_transactions.csv')
print(f"Seeding {len(df_trx)} transactions...")

for _, row in df_trx.iterrows():
    db.add(models.Transaction(
        trx_id             = int(row['trx_id']),
        user_id            = int(row['user_id']),
        timestamp          = pd.to_datetime(row['timestamp']),
        category           = str(row['category']),
        merchant_name      = str(row['merchant_name']),
        transaction_method = str(row['transaction_method']),
        amount             = float(row['amount']),
        days_ago           = 0,
        week_status        = "Weekday"
    ))

db.commit()
print("✓ Transaction selesai")

# Interaction
df_int = pd.read_csv('fact_interactions.csv')
print(f"Seeding {len(df_int)} interactions...")

for _, row in df_int.iterrows():
    db.add(models.Interaction(
        log_id           = int(row['log_id']),
        user_id          = int(row['user_id']),
        session_id       = int(row['session_id']),
        timestamp        = pd.to_datetime(row['timestamp']),
        feature_accessed = str(row['feature_accessed']),
        action           = str(row['action'])
    ))

db.commit()
print("✓ Interaction selesai")

db.close()
print("\n✅ Seeding database selesai")