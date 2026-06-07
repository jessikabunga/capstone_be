from sqlalchemy import Column, String, Integer, Numeric, Boolean, ForeignKey, TIMESTAMP, DateTime, Date, Text, func
from database import Base

class Profile(Base):
    __tablename__ = "dim_profile"
    user_id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    account_number = Column(String(20), unique=True, index=True)
    full_name = Column(String(255))
    place_of_birth = Column(String(100))
    date_of_birth = Column(Date) 
    national_id = Column(String(16), unique=True)
    email_address = Column(String(100), unique=True)
    pin_hash = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    phone_number = Column(String(20))
    street_address = Column(String(255)) 
    city = Column(String(100))
    province = Column(String(100))
    age = Column(Integer)
    occupation = Column(String(100))
    monthly_income = Column(Numeric(15,2), default=0.00)
    account_balance = Column(Numeric(15,2), default=0.00)
    consent_personalization = Column(Boolean, default=False)

    is_admin = Column(Boolean, default=False)
    segment_ground_truth = Column(String, nullable=True)

class ClusteringResult(Base):
    __tablename__ = "clustering_results"

    user_id                   = Column(Integer, ForeignKey("dim_profile.user_id"), primary_key=True)
    cluster_id                = Column(Integer)
    predicted_cta             = Column(String(100))
    generated_message         = Column(Text, nullable=True)
    category_focus            = Column(String(100))
    trigger_reason            = Column(String,  nullable=True)
    recommendation_confidence = Column(Numeric(5, 4))
    timestamp                 = Column(DateTime(timezone=True))

class Transaction(Base):
    __tablename__ = "fact_transactions"

    trx_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_profile.user_id"))
    timestamp = Column(DateTime(timezone=True))
    category = Column(String(100))
    merchant_name = Column(String(100))
    transaction_method = Column(String(50))
    amount = Column(Numeric(15, 2))
    days_ago = Column(Integer)
    week_status = Column(String(50))
    recipient_bank = Column(String(100), nullable=True)
    recipient_account = Column(String(50), nullable=True)

class Interaction(Base):
    __tablename__ = "fact_interactions"

    log_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_profile.user_id"))
    session_id = Column(Integer)
    timestamp = Column(DateTime(timezone=True))
    feature_accessed = Column(String(100))
    action = Column(String(50))
    interaction_type = Column(String(50), nullable=True)

class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id         = Column(Integer, primary_key=True, index=True)
    token      = Column(String, unique=True, nullable=False, index=True)
    blacklisted_at = Column(DateTime(timezone=True), nullable=False)

class SavedContact(Base):
    __tablename__ = "saved_contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("dim_profile.user_id"))
    name = Column(String(100), nullable=False)
    account_number = Column(String(50), nullable=False)
    bank_name = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False)  # 'Transfer' or 'TopUp' / other provider types
