from sqlalchemy import Column, String, Integer, Numeric, Boolean, ForeignKey, TIMESTAMP, Date
from database import Base

class Profile(Base):
    __tablename__ = "dim_profile"

    user_id = Column(String(50), primary_key=True, index=True)
    full_name = Column(String(255))
    consent_personalization = Column(Boolean, default=False)
    occupation = Column(String(100))

class ClusteringResult(Base):
    __tablename__ = "clustering_results"

    user_id = Column(String(50), ForeignKey("dim_profile.user_id"), primary_key=True)
    cluster_id = Column(Integer)
    last_updated = Column(TIMESTAMP)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    email = Column(String, unique=True)

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    full_name = Column(String)
    dob = Column(Date) # TTL
    nik = Column(String, unique=True)
    occupation = Column(String)
    
    phone_number = Column(String)
    address = Column(String)
    city = Column(String)
    province = Column(String)
    
    consent_personalization = Column(Boolean, default=False)