from sqlalchemy import Column, Float, String, Integer, Numeric, Boolean, ForeignKey, TIMESTAMP, DateTime, Date
from database import Base

class Profile(Base):
    __tablename__ = "dim_profile"
    user_id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    account_number = Column(String(20), unique=True, index=True)
    full_name = Column(String(255))
    birth_place = Column(String(100))
    birth_date = Column(Date) 
    national_id = Column(String(20), unique=True)
    email_address = Column(String(100), unique=True)
    pin_hash = Column(String(255))
    created_at = Column(DateTime)
    phone_number = Column(String(20))
    street_address = Column(String(255)) 
    city = Column(String(100))
    province = Column(String(100))
    age = Column(Integer)
    occupation = Column(String(100))
    monthly_income = Column(Float, default=0.0)
    account_balance = Column(Float, default=0.0)
    consent_personalization = Column(Boolean, default=False)

class ClusteringResult(Base):
    __tablename__ = "clustering_results"

    user_id = Column(Integer, ForeignKey("dim_profile.user_id"), primary_key=True)
    cluster_id = Column(Integer)
    last_updated = Column(TIMESTAMP)

class Transaction(Base):
    __tablename__ = "fact_transactions"

    trx_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_profile.user_id"))
    timestamp = Column(DateTime)
    category = Column(String(100))
    merchant_name = Column(String(100))
    transaction_method = Column(String(50))
    amount = Column(Float)

class Interaction(Base):
    __tablename__ = "fact_interactions"

    log_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_profile.user_id"))
    session_id = Column(String(50))
    timestamp = Column(DateTime)
    feature_accessed = Column(String(100))
    action = Column(String(50))
