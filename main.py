from enum import Enum
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models 
import schemas
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import re
from pydantic import BaseModel, Field, EmailStr, field_validator
from datetime import date
from fastapi.middleware.cors import CORSMiddleware
import random

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
    username: str = Field(
        min_length=5, 
        max_length=20,
        
        description="Username harus terdiri dari 5 hingga 20 karakter"
    )
    email_address: EmailStr 
    password: str = Field(
        min_length=6,
        max_length=12,
        description="Password harus 6-12 karakter dan mengandung huruf, angka, serta simbol"
    )

    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v):
        pattern = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&.,_\\-])[A-Za-z\d@$!%*#?&.,_\\-]+$"
        if not re.match(pattern, v):
            raise ValueError("Password harus mengandung huruf, angka, serta simbol (@$!%*#?&)")
        return v

class OccupationChoice(str, Enum):
    pelajar_mahasiswa = "Pelajar / Mahasiswa"
    fresh_graduate = "Fresh Graduate"
    karyawan_swasta = "Karyawan Swasta"
    pns = "PNS"
    pengusaha = "Pengusaha / Wirausaha"
    profesional = "Profesional"
    freelancer = "Freelancer"

class ProfileCreate(BaseModel):
    full_name: str = Field(
        min_length=5, 
        max_length=20, 
        pattern=r"^[a-zA-Z\s.,]+$",
        description="Nama lengkap beserta gelar jika ada"
    )
    birth_place: str
    birth_date: date 
    national_id: str = Field(pattern=r"^\d{16}$")
    occupation: OccupationChoice
    phone_number: str = Field(pattern=r"^\d{10,14}$")
    street_address: str = Field(min_length=10, max_length=255)
    city: str = Field(min_length=2, max_length=50)
    province: str = Field(min_length=4, max_length=50)
    monthly_income: float = Field(default=0.0)
    consent_personalization: bool
    
    pin: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="PIN 6 digit angka untuk transaksi"
    )

    
    @field_validator('birth_date')
    @classmethod
    def check_birth_date(cls, v):
        if v > date.today():
            raise ValueError("Tanggal lahir tidak masuk akal (masa depan)")
        return v

    @field_validator('national_id', 'phone_number')
    @classmethod
    def check_not_all_same_digits(cls, v):
        if len(set(v)) == 1:
            raise ValueError("Data tidak boleh berisi angka yang sama semua")
        return v
    
app = FastAPI(title="CIMB Capstone")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print("VALIDATION ERROR:", exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# ==========================================
# DICTIONARY PROMO
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

# ==========================================
# ENDPOINTS / API
# ==========================================

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
        
    user = db.query(models.Profile).filter(models.Profile.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@app.get("/")
def read_root():
    return {"message": "Backend API is Running!"}

@app.post("/register", tags=["Auth"])
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(models.Profile).filter(models.Profile.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username sudah dipakai!")

    if db.query(models.Profile).filter(models.Profile.email_address == user.email_address).first():
        raise HTTPException(status_code=400, detail="Email sudah terdaftar!")
    
    hashed_pw = get_password_hash(user.password)
    
    new_user = models.Profile(
        username=user.username, 
        email_address=user.email_address,
        password_hash=hashed_pw
    )
    db.add(new_user)
    db.commit()
    return {"message": "Akun berhasil dibuat, silakan lanjut isi profil"}

@app.post("/login", tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Profile).filter(models.Profile.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/profile", tags=["User Profile"])
def create_profile(data: ProfileCreate, db: Session = Depends(get_db), current_user: models.Profile = Depends(get_current_user)):
    
    if current_user.full_name:
        raise HTTPException(status_code=400, detail="Profil sudah diisi")

    profile_dict = data.model_dump()
    
    raw_pin = profile_dict.pop("pin")
    current_user.pin_hash = get_password_hash(raw_pin)
    
    current_user.account_number = "".join([str(random.randint(0, 9)) for _ in range(10)])
    
    current_user.account_balance = 0.0 

    today = date.today()
    birth_date = data.birth_date
    calculated_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    current_user.age = calculated_age
    
    for key, value in profile_dict.items():
        setattr(current_user, key, value)
    
    db.commit()
    db.refresh(current_user)
    
    return {
        "status": "success",
        "message": "Profil berhasil dibuat",
        "data": {
            "account_number": current_user.account_number,
            "account_balance": current_user.account_balance,
            "age": current_user.age,
            "balance": current_user.account_balance
        }
    }

@app.get("/profile", tags=["User Profile"])
def get_profile(current_user: models.Profile = Depends(get_current_user)):
    if not current_user.full_name:
        raise HTTPException(status_code=404, detail="Profil belum diisi")
    return {
        "full_name": current_user.full_name,
        "national_id": current_user.national_id,
        "birth_place": current_user.birth_place,
        "birth_date": str(current_user.birth_date) if current_user.birth_date else None,
        "email_address": current_user.email_address,
        "phone_number": current_user.phone_number,
        "occupation": current_user.occupation,
        "monthly_income": current_user.monthly_income,
        "street_address": current_user.street_address,
        "city": current_user.city,
        "province": current_user.province,
        "age": current_user.age,
        "account_number": current_user.account_number,  
        "account_balance": current_user.account_balance, 
        "consent_personalization": current_user.consent_personalization,
    }

class ConsentUpdate(BaseModel):
    consent_personalization: bool

@app.patch("/profile/consent", tags=["User Profile"])
def update_consent(data: ConsentUpdate, current_user: models.Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.consent_personalization = data.consent_personalization
    db.commit()
    return {"message": "Consent updated", "consent_personalization": current_user.consent_personalization}

models.Base.metadata.create_all(bind=engine)

# Tanpa ML
@app.get("/recommendation", response_model=schemas.PromoResponse)
def get_recommendation(current_user: models.Profile = Depends(get_current_user)):
    if not current_user.full_name:
        raise HTTPException(status_code=404, detail="Profil belum diisi, silakan isi profil terlebih dahulu")

    if current_user.consent_personalization == False:
        return schemas.PromoResponse(
            user_id=current_user.user_id,
            message="User opted out of personalization",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"]
        )
    
    pekerjaan = current_user.occupation.lower()
    
    if "mahasiswa" in pekerjaan or "pelajar" in pekerjaan:
        cluster_id = 1
    elif "fresh graduate" in pekerjaan or "karyawan" in pekerjaan:
        cluster_id = 2
    elif "pengusaha" in pekerjaan or "pns" in pekerjaan or "profesional" in pekerjaan:
        cluster_id = 3
    elif "freelance" in pekerjaan:
        cluster_id = 4
    else:
        cluster_id = 2

    selected_promo = PROMO_CATALOG[cluster_id]
    
    return schemas.PromoResponse(
        user_id=current_user.user_id,
        message=f"Success getting promo for {current_user.occupation}",
        promo_title=selected_promo["title"],
        promo_type=selected_promo["type"]
    )

# Pakai ML
# @app.get("/recommendation", response_model=schemas.PromoResponse)
# def get_recommendation(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     user_profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    
#     if not user_profile:
#         raise HTTPException(status_code=404, detail="Profil belum diisi, silakan isi profil terlebih dahulu")

#     if user_profile.consent_personalization == False:
#         return schemas.PromoResponse(
#             user_id=current_user.id,
#             message="User opted out of personalization",
#             promo_title=PROMO_CATALOG["general"]["title"],
#             promo_type=PROMO_CATALOG["general"]["type"]
#         )
    
#     ml_result = db.query(models.ClusteringResult).filter(models.ClusteringResult.user_id == current_user.id).first()
    
#     if not ml_result or ml_result.cluster_id not in PROMO_CATALOG:
#         return schemas.PromoResponse(
#             user_id=current_user.id,
#             message="Data ML belum siap, mengirim promo default",
#             promo_title=PROMO_CATALOG["general"]["title"],
#             promo_type=PROMO_CATALOG["general"]["type"]
#         )

#     selected_promo = PROMO_CATALOG[ml_result.cluster_id]
    
#     return schemas.PromoResponse(
#         user_id=current_user.id,
#         message=f"Success getting promo for {user_profile.occupation}",
#         promo_title=selected_promo["title"],
#         promo_type=selected_promo["type"]
#     )