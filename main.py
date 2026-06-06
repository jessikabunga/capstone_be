from enum import Enum
from fastapi import FastAPI, Depends, HTTPException, status, Query
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
from decimal import Decimal
from sqlalchemy import func

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

# PYDANTIC SCHEMAS (Request Models)
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

# class OccupationChoice(str, Enum):
#     pelajar_mahasiswa = "Pelajar / Mahasiswa"
#     fresh_graduate = "Fresh Graduate"
#     karyawan_swasta = "Karyawan Swasta"
#     pns = "PNS"
#     pengusaha = "Pengusaha / Wirausaha"
#     profesional = "Profesional"
#     freelancer = "Freelancer"

# Dataset Shinta
class OccupationChoice(str, Enum):
    student = "Student"
    fresh_graduate = "Fresh Graduate"
    private_employee = "Private Employee"
    civil_servant = "Civil Servant"
    doctor = "Doctor"
    lawyer = "Lawyer"
    entrepreneur = "Entrepreneur"
    freelancer = "Freelancer"

class ProfileCreate(BaseModel):
    full_name: str = Field(
        min_length=5, 
        max_length=20, 
        pattern=r"^[a-zA-Z\s.,]+$",
        description="Nama lengkap beserta gelar jika ada"
    )
    place_of_birth: str
    date_of_birth: date 
    national_id: str = Field(pattern=r"^\d{16}$")
    occupation: OccupationChoice
    phone_number: str = Field(pattern=r"^\d{10,14}$")
    street_address: str = Field(min_length=10, max_length=255)
    city: str = Field(min_length=2, max_length=50)
    province: str = Field(min_length=4, max_length=50)
    monthly_income: Decimal = Field(default=Decimal('0.00'))
    consent_personalization: bool
    pin: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="PIN 6 digit angka untuk transaksi"
    )

    
    @field_validator('date_of_birth')
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
    
class ConsentUpdate(BaseModel):
    consent_personalization: bool

class AccountValidationRequest(BaseModel):
    bank_name: str
    account_number: str

class TransferRequest(BaseModel):
    recipient_name: str
    recipient_bank: str
    recipient_account: str
    amount: Decimal
    notes: str | None = None
    pin: str

# ==========================================
# APP Init   
# ==========================================
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

# DICTIONARY PROMO
# ==========================================
# 0 = Student
# 1 = Young Professional
# 2 = Established Professional
# 3 = Freelancer
PROMO_CATALOG = {
    0: {"title": "Diskon 50% QRIS Kopi Kenangan & Mie Gacoan!", "type": "Promo #1"},
    1: {"title": "Cashback Top Up E-Wallet s/d Rp 50.000", "type": "Promo #2"},
    2: {"title": "Penawaran Spesial: Limit Kartu Kredit s/d 50 Juta", "type": "Promo #3"},
    3: {"title": "Bebas Biaya Transfer Antar Bank Selama Sebulan!", "type": "Promo #1"},
    "general": {"title": "Waspada Penipuan! Jaga Kerahasiaan PIN Anda", "type": "Non-Promo"}
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

models.Base.metadata.create_all(bind=engine)

# ==========================================
# Auth Helper
# ==========================================
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    is_blacklisted = db.query(models.TokenBlacklist).filter(
        models.TokenBlacklist.token == token
    ).first()
    if is_blacklisted:
        raise credentials_exception

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

def get_admin_user(current_user: models.Profile = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya admin yang diizinkan."
        )
    return current_user

# ==========================================
# ENDPOINT
# ==========================================
@app.get("/")
def read_root():
    return {"message": "Backend API is Running!"}

# Auth
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

@app.post("/logout", tags=["Auth"])
def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_current_user)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Token tidak valid")

    blacklisted = models.TokenBlacklist(
        token=token,
        blacklisted_at=datetime.now(timezone.utc)
    )
    db.add(blacklisted)
    db.commit()

    return {"message": "Logout berhasil"}

# ==========================================
# User Profile
# ==========================================
@app.post("/profile", tags=["User Profile"])
def create_profile(
    data: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_current_user)
):
    if current_user.full_name:
        raise HTTPException(status_code=400, detail="Profil sudah diisi")

    profile_dict = data.model_dump()

    raw_pin = profile_dict.pop("pin")
    current_user.pin_hash = get_password_hash(raw_pin)
    current_user.account_number = "".join([str(random.randint(0, 9)) for _ in range(10)])
    current_user.account_balance = Decimal('0.00')

    today = date.today()
    date_of_birth = data.date_of_birth
    calculated_age = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )
    current_user.age = calculated_age

    for key, value in profile_dict.items():
        if hasattr(value, 'value'):
            value = value.value
        setattr(current_user, key, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profil berhasil dibuat",
        "data": {
            "account_number": current_user.account_number,
            "account_balance": current_user.account_balance,
            "age": current_user.age,
        }
    }

@app.get("/profile", tags=["User Profile"])
def get_profile(current_user: models.Profile = Depends(get_current_user)):
    if not current_user.full_name:
        raise HTTPException(status_code=404, detail="Profil belum diisi")
    return {
        "user_id": current_user.user_id,
        "full_name": current_user.full_name,
        "national_id": current_user.national_id,
        "place_of_birth": current_user.place_of_birth,
        "date_of_birth": str(current_user.date_of_birth) if current_user.date_of_birth else None,
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



@app.patch("/profile/consent", tags=["User Profile"])
def update_consent(data: ConsentUpdate, current_user: models.Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.consent_personalization = data.consent_personalization
    db.commit()
    return {
        "message": "Consent updated", 
        "consent_personalization": current_user.consent_personalization
    }

# ==========================================
# Transaksi terbaru
# ==========================================
@app.get("/transactions/recent", tags=["User Profile"])
def get_recent_transactions(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: models.Profile = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    FR-02: Menampilkan aktivitas transaksi terbaru untuk halaman beranda.
    Default 5 transaksi, maksimal 20. Frontend bisa kirim ?limit=10.
    """
    if not current_user.full_name:
        raise HTTPException(status_code=404, detail="Profil belum diisi")
 
    recent_trx = (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == current_user.user_id)
        .order_by(models.Transaction.timestamp.desc())
        .limit(limit)
        .all()
    )
 
    return {
        "user_id": current_user.user_id,
        "transactions": [
            {
                "trx_id": trx.trx_id,
                "timestamp": str(trx.timestamp),
                "category": trx.category,
                "merchant_name": trx.merchant_name,
                "transaction_method": trx.transaction_method,
                "amount": trx.amount,
            }
            for trx in recent_trx
        ]
    }

@app.post("/validate-account", tags=["User Profile"])
def validate_account(
    data: AccountValidationRequest,
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_current_user)
):
    bank_name_clean = data.bank_name.strip().upper()
    acc_num = data.account_number.strip()

    if bank_name_clean == "CIMB NIAGA":
        profile = db.query(models.Profile).filter(models.Profile.account_number == acc_num).first()
        if not profile:
            raise HTTPException(status_code=400, detail="Nomor rekening CIMB Niaga tidak ditemukan!")
        return {"account_name": profile.full_name}
    else:
        bank_label = data.bank_name.upper().replace("BANK ", "")
        return {"account_name": f"Penerima {bank_label} ({acc_num[-4:]})"}

@app.post("/transfer", tags=["User Profile"])
def process_transfer(
    data: TransferRequest,
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_current_user)
):
    if not current_user.pin_hash:
        raise HTTPException(status_code=400, detail="PIN belum diatur di profil Anda!")
    
    if not verify_password(data.pin, current_user.pin_hash):
        raise HTTPException(status_code=400, detail="PIN yang Anda masukkan salah!")

    if current_user.account_balance < data.amount:
        raise HTTPException(
            status_code=400,
            detail="Saldo Anda tidak mencukupi untuk melakukan transaksi ini."
        )

    current_user.account_balance -= data.amount

    bank_lower = data.recipient_bank.lower()
    category = "Transfer"
    if "pay" in bank_lower or "wallet" in bank_lower or bank_lower in ["gopay", "ovo", "dana", "linkaja", "shopeepay"]:
        category = "E-Wallet"

    new_trx = models.Transaction(
        user_id=current_user.user_id,
        timestamp=datetime.now(timezone.utc),
        category=category,
        merchant_name=data.recipient_name,
        transaction_method="Transfer",
        amount=data.amount,
        days_ago=0,
        week_status="Weekday" if datetime.now(timezone.utc).weekday() < 5 else "Weekend"
    )
    db.add(current_user)
    db.add(new_trx)
    db.commit()

    return {
        "status": "success",
        "message": "Transfer berhasil",
        "new_balance": float(current_user.account_balance)
    }

@app.post("/transaction", tags=["Transaction"])
def process_transaction(
    data: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_current_user)
):
    if not current_user.pin_hash:
        raise HTTPException(status_code=400, detail="PIN belum diatur di profil Anda!")
    
    if not verify_password(data.pin, current_user.pin_hash):
        raise HTTPException(status_code=400, detail="PIN yang Anda masukkan salah!")

    if current_user.account_balance < data.amount:
        raise HTTPException(
            status_code=400,
            detail="Saldo Anda tidak mencukupi untuk melakukan transaksi ini."
        )

    current_user.account_balance -= data.amount

    new_trx = models.Transaction(
        user_id=current_user.user_id,
        timestamp=datetime.now(timezone.utc),
        category=data.category,
        merchant_name=data.merchant_name,
        transaction_method=data.transaction_method,
        amount=data.amount,
        days_ago=0,
        week_status="Weekday" if datetime.now(timezone.utc).weekday() < 5 else "Weekend"
    )
    db.add(current_user)
    db.add(new_trx)
    db.commit()

    return {
        "status": "success",
        "message": "Transaksi berhasil",
        "new_balance": float(current_user.account_balance)
    }

QRIS_MERCHANTS = {
    "MRC_GOJEK": {
        "merchant_id": "MRC_GOJEK",
        "merchant_name": "Gojek",
        "category": "Transport & Mobility",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_GRAB": {
        "merchant_id": "MRC_GRAB",
        "merchant_name": "Grab",
        "category": "Transport & Mobility",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_STARBUCKS": {
        "merchant_id": "MRC_STARBUCKS",
        "merchant_name": "Starbucks",
        "category": "Food & Beverage",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_JANJI_JIWA": {
        "merchant_id": "MRC_JANJI_JIWA",
        "merchant_name": "Janji Jiwa",
        "category": "Food & Beverage",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_KOPI_KENANGAN": {
        "merchant_id": "MRC_KOPI_KENANGAN",
        "merchant_name": "Kopi Kenangan",
        "category": "Food & Beverage",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_MCD": {
        "merchant_id": "MRC_MCD",
        "merchant_name": "McD",
        "category": "Food & Beverage",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_INDOMARET": {
        "merchant_id": "MRC_INDOMARET",
        "merchant_name": "Indomaret",
        "category": "Retail & Convenience",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_ALFAMART": {
        "merchant_id": "MRC_ALFAMART",
        "merchant_name": "Alfamart",
        "category": "Retail & Convenience",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    },
    "MRC_FAMILYMART": {
        "merchant_id": "MRC_FAMILYMART",
        "merchant_name": "FamilyMart",
        "category": "Retail & Convenience",
        "transaction_method": "QRIS",
        "qr_version": "1.0"
    }
}

@app.get("/qr/decode/{payload}", tags=["Transaction"])
def decode_qr(payload: str, current_user: models.Profile = Depends(get_current_user)):
    if payload not in QRIS_MERCHANTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant QRIS tidak terdaftar atau tidak valid!"
        )
    return QRIS_MERCHANTS[payload]


# ==========================================
# Rekomendasi & Insight
# ==========================================
@app.get("/recommendation", response_model=schemas.PromoResponse, tags=["Recommendation"])
def get_recommendation(
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_current_user)
):
    if not current_user.full_name:
        raise HTTPException(
            status_code=404,
            detail="Profil belum diisi, silakan isi profil terlebih dahulu"
        )
 
    if not current_user.consent_personalization:
        return schemas.PromoResponse(
            user_id=current_user.user_id,
            message="Aktifkan personalisasi untuk mendapatkan rekomendasi yang relevan untukmu",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"],
            generated_message=(
                "Kamu belum mengaktifkan personalisasi. "
                "Aktifkan sekarang agar kami bisa memberikan insight dan promo "
                "yang sesuai dengan kebiasaan transaksimu."
            ),
            predicted_cta="Aktifkan Personalisasi",
            cta_url="/profile/consent",
            trigger_reason="Personalisasi belum aktif",
            category_focus=None
        )
 
    ml_result = db.query(models.ClusteringResult).filter(
        models.ClusteringResult.user_id == current_user.user_id
    ).first()
 
    if not ml_result or ml_result.cluster_id not in PROMO_CATALOG:
        return schemas.PromoResponse(
            user_id=current_user.user_id,
            message="Data ML belum siap, mengirim promo default",
            promo_title=PROMO_CATALOG["general"]["title"],
            promo_type=PROMO_CATALOG["general"]["type"],
            generated_message="Tetap aman bertransaksi bersama CIMB.",
            predicted_cta="Pelajari Selengkapnya",
            cta_url=None,
            trigger_reason=None,
            category_focus=None
        )
 
    selected_promo = PROMO_CATALOG[ml_result.cluster_id]
 
    return schemas.PromoResponse(
        user_id=current_user.user_id,
        message=f"Success getting promo for {current_user.occupation}",
        promo_title=selected_promo["title"],
        promo_type=selected_promo["type"],
        generated_message=getattr(ml_result, 'generated_message', selected_promo["title"]),
        predicted_cta=getattr(ml_result, 'predicted_cta', "Ambil Promo"),
        cta_url=None,
        trigger_reason=getattr(ml_result, 'trigger_reason', None),
        category_focus=getattr(ml_result, 'category_focus', None)
    )

# ==========================================
# Tracking
# ==========================================
@app.post("/api/v1/track", tags=["Tracking"], status_code=201)
def track_user_interaction(
    interaction: schemas.InteractionCreate, 
    db: Session = Depends(get_db)
):
    VALID_INTERACTION_TYPES = {"banner_click", "insight_view", "cta_click", "feature_click"}
    if hasattr(interaction, 'interaction_type') and interaction.interaction_type:
        if interaction.interaction_type not in VALID_INTERACTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"interaction_type tidak valid. Gunakan salah satu dari: {VALID_INTERACTION_TYPES}"
            )
        
    try:
        new_log = models.Interaction(
            user_id=interaction.user_id,
            session_id=interaction.session_id,
            timestamp=datetime.now(timezone.utc), 
            feature_accessed=interaction.feature_accessed,
            action=interaction.action,

            interaction_type=getattr(interaction, 'interaction_type', None)
        )
        
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        
        return {
            "status": "success", 
            "message": "Aktivitas berhasil dicatat",
            "log_id": new_log.log_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Terjadi kesalahan saat mencatat log: {str(e)}"
        )
    
# ==========================================
# Admin Dashboard
# ==========================================
@app.get("/api/v1/admin/dashboard-stats", tags=["Admin Dashboard"])
def get_dashboard_stats(
    start_date: str = Query(default=None, description="Filter dari tanggal (YYYY-MM-DD)"),
    end_date: str   = Query(default=None, description="Filter sampai tanggal (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: models.Profile = Depends(get_admin_user) 
):
    try:
        dt_start = None
        dt_end = None
        if start_date:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_date:
            dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
 
        trx_query = db.query(models.Transaction)
        if dt_start:
            trx_query = trx_query.filter(models.Transaction.timestamp >= dt_start)
        if dt_end:
            trx_query = trx_query.filter(models.Transaction.timestamp <= dt_end)
 
        total_volume = db.query(
            func.sum(models.Transaction.amount)
        ).scalar() or Decimal('0')
 
        payment_methods = db.query(
            models.Transaction.transaction_method,
            func.count(models.Transaction.trx_id).label("total_transaksi"),
            func.sum(models.Transaction.amount).label("total_nominal")
        ).group_by(models.Transaction.transaction_method).all()
 
        category_stats = db.query(
            models.Transaction.category,
            func.count(models.Transaction.trx_id).label("total_transaksi"),
            func.sum(models.Transaction.amount).label("total_nominal")
        ).group_by(models.Transaction.category).order_by(
            func.sum(models.Transaction.amount).desc()
        ).all()
 
        total_users = db.query(func.count(models.Profile.user_id)).scalar() or 0
        consent_true_count = db.query(func.count(models.Profile.user_id)).filter(
            models.Profile.consent_personalization == True
        ).scalar() or 0
        consent_rate = round((consent_true_count / total_users * 100), 2) if total_users > 0 else 0
 
        segment_transaction_stats = db.query(
            models.Profile.occupation,
            func.count(models.Transaction.trx_id).label("total_transaksi"),
            func.sum(models.Transaction.amount).label("total_nominal")
        ).join(
            models.Transaction, models.Profile.user_id == models.Transaction.user_id
        ).filter(
            models.Profile.consent_personalization == True
        ).group_by(models.Profile.occupation).all()
 
        cluster_transaction_stats = db.query(
            models.ClusteringResult.cluster_id,
            func.count(models.Transaction.trx_id).label("total_transaksi"),
            func.sum(models.Transaction.amount).label("total_nominal")
        ).join(
            models.Transaction,
            models.ClusteringResult.user_id == models.Transaction.user_id
        ).group_by(models.ClusteringResult.cluster_id).all()
 
        cta_conversions = db.query(
            models.Interaction.feature_accessed,
            func.count(models.Interaction.log_id).label("total_clicks")
        ).filter(
            models.Interaction.action == "click"
        ).group_by(models.Interaction.feature_accessed).all()
 
        engagement_query = db.query(
            func.date(models.Interaction.timestamp).label("tanggal"),
            func.count(models.Interaction.log_id).label("total_interaksi")
        )
        if dt_start:
            engagement_query = engagement_query.filter(models.Interaction.timestamp >= dt_start)
        if dt_end:
            engagement_query = engagement_query.filter(models.Interaction.timestamp <= dt_end)
        engagement_per_day = engagement_query.group_by(
            func.date(models.Interaction.timestamp)
        ).order_by(func.date(models.Interaction.timestamp)).all()
 
        interaction_type_stats = db.query(
            models.Interaction.interaction_type,
            func.count(models.Interaction.log_id).label("total")
        ).filter(
            models.Interaction.interaction_type.isnot(None)
        ).group_by(models.Interaction.interaction_type).all()
 
        feature_by_cluster = db.query(
            models.ClusteringResult.cluster_id,
            models.Interaction.feature_accessed,
            func.count(models.Interaction.log_id).label("total_clicks")
        ).join(
            models.Interaction,
            models.ClusteringResult.user_id == models.Interaction.user_id
        ).group_by(
            models.ClusteringResult.cluster_id,
            models.Interaction.feature_accessed
        ).order_by(
            models.ClusteringResult.cluster_id,
            func.count(models.Interaction.log_id).desc()
        ).all()
 
        return {
            "filter": {
                "start_date": start_date,
                "end_date": end_date
            },
            "summary": {
                "total_users_registered": total_users,
                "consent_rate_percentage": consent_rate,
                "total_all_transaction_volume": total_volume
            },
            "charts": {
                "payment_methods_usage": [
                    {
                        "method": row.transaction_method,
                        "count": row.total_transaksi,
                        "amount": row.total_nominal
                    } for row in payment_methods
                ],
                "spending_categories": [
                    {
                        "category": row.category,
                        "count": row.total_transaksi,
                        "amount": row.total_nominal
                    } for row in category_stats
                ],
                "personalized_transactions_by_occupation": [
                    {
                        "occupation": row.occupation,
                        "count": row.total_transaksi,
                        "amount": row.total_nominal
                    } for row in segment_transaction_stats
                ],
                "transactions_by_cluster": [
                    {
                        "cluster_id": row.cluster_id,
                        "count": row.total_transaksi,
                        "amount": row.total_nominal
                    } for row in cluster_transaction_stats
                ],
                "cta_conversion_rates": [
                    {
                        "feature": row.feature_accessed,
                        "total_clicks": row.total_clicks
                    } for row in cta_conversions
                ],
                "engagement_per_day": [
                    {
                        "date": str(row.tanggal),
                        "total_interactions": row.total_interaksi
                    } for row in engagement_per_day
                ],
                "interaction_by_type": [
                    {
                        "interaction_type": row.interaction_type,
                        "total": row.total
                    } for row in interaction_type_stats
                ],
                "feature_usage_by_cluster": [
                    {
                        "cluster_id": row.cluster_id,
                        "feature": row.feature_accessed,
                        "total_clicks": row.total_clicks
                    } for row in feature_by_cluster
                ]
            }
        }
 
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memproses data dashboard finansial: {str(e)}"
        )

# ==========================================
# Admin Tools
# ==========================================
@app.post("/admin/trigger-batch", tags=["Admin Tools"])
def trigger_ml_pipeline(
    current_user: models.Profile = Depends(get_admin_user)
):
    try:
        from batch_predict import run_batch_prediction
        run_batch_prediction()
        return {
            "status": "success", 
            "message": "ML Pipeline berhasil dijalankan secara manual."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline gagal: {str(e)}")