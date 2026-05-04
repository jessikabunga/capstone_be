from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Ganti dengan username, password, dan nama database PostgreSQL kamu
# Format: postgresql://username:password@localhost/nama_database
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:bunga235@localhost:5432/capstone_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Fungsi untuk membuka koneksi ke database tiap kali ada request API
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()