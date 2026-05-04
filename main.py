from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models 
from models import User
import schemas
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "capstone_kelompok_3"
ALGORITHM = "HS256"

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

class UserCreate(BaseModel):
    username: str
    password: str

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="CIMB Capstone")

# ==========================================
# DICTIONARY PROMO (Berdasarkan Flowchart PM)
# ==========================================
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@app.get("/")
def read_root():
    return {"message": "Backend API is Running!"}

@app.post("/register", tags=["Auth"])
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username sudah terdaftar")
    
    hashed_pw = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    return {"message": "User berhasil didaftarkan!"}

@app.post("/login", tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/recommendation/{user_id}", response_model=schemas.PromoResponse)
def get_recommendation(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    
    user = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    if user.consent_personalization == False:
        return schemas.PromoResponse(
            user_id=user.user_id,
            message="User opted out of personalization",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"]
        )
    
    ml_result = db.query(models.ClusteringResult).filter(models.ClusteringResult.user_id == user_id).first()
    
    if not ml_result or ml_result.cluster_id not in PROMO_CATALOG:
        return schemas.PromoResponse(
            user_id=user.user_id,
            message="Data ML belum siap, mengirim promo default",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"]
        )

    selected_promo = PROMO_CATALOG[ml_result.cluster_id]
    
    return schemas.PromoResponse(
        user_id=user.user_id,
        message=f"Success getting promo for {user.occupation}",
        promo_title=selected_promo["title"],
        promo_type=selected_promo["type"]
    )