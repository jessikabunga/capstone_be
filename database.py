from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Format: postgresql://username:password@localhost/nama_database
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:password@localhost/database"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
