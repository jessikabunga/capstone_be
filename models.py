from sqlalchemy import Column, String, Integer, Numeric, Boolean, ForeignKey, TIMESTAMP
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