import pandas as pd
import joblib
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
import models
from datetime import datetime, timezone


def build_scv_from_db(db: Session) -> pd.DataFrame:
    rows = db.query(
        models.Profile.user_id,
        models.Profile.occupation,
        models.Profile.monthly_income,
        models.Profile.account_balance,
        models.Profile.age,
    ).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([r._asdict() for r in rows])

    trx_rows = db.query(
        models.Transaction.user_id,
        func.count(models.Transaction.trx_id).label('total_trx'),
        func.sum(models.Transaction.amount).label('total_spend'),
    ).group_by(models.Transaction.user_id).all()

    if trx_rows:
        trx_df = pd.DataFrame([r._asdict() for r in trx_rows])
        df = df.merge(trx_df, on='user_id', how='left')
    else:
        df['total_trx']   = 0
        df['total_spend'] = 0

    df['total_trx']   = df['total_trx'].fillna(0)
    df['total_spend'] = df['total_spend'].fillna(0).astype(float)
    df['monthly_income']   = df['monthly_income'].fillna(0).astype(float)
    df['account_balance']  = df['account_balance'].fillna(0).astype(float)
    df['age']              = df['age'].fillna(25).astype(int)

    fav_rows = db.query(
        models.Transaction.user_id,
        models.Transaction.category,
        func.count(models.Transaction.trx_id).label('cnt')
    ).group_by(
        models.Transaction.user_id,
        models.Transaction.category
    ).all()

    if fav_rows:
        fav_df = pd.DataFrame([r._asdict() for r in fav_rows])
        fav_df = fav_df.sort_values('cnt', ascending=False).drop_duplicates('user_id')
        fav_df = fav_df.rename(columns={'category': 'fav_category'})[['user_id', 'fav_category']]
        df = df.merge(fav_df, on='user_id', how='left')
    
    df['fav_category'] = df.get('fav_category', pd.Series(['Retail & Convenience'] * len(df)))
    df['fav_category'] = df['fav_category'].fillna('Retail & Convenience')

    df['spend_to_income'] = df['total_spend'] / (df['monthly_income'] + 1)

    return df


# ============================================
# Auto triger untuk data massal
# ============================================
def run_batch_prediction():
    print("Memulai pipeline batch prediction ML...")
    db: Session = SessionLocal()

    # ===========================================================================
    # 1. LOAD ML ARTIFACTS
    # ===========================================================================
    try:
        scaler                  = joblib.load('scaler_clustering.pkl')
        kmeans                  = joblib.load('kmeans_model.pkl')
        rf_model                = joblib.load('rf_cta_model.pkl')
        le_cta                  = joblib.load('label_encoder_cta.pkl')
        rf_features             = joblib.load('feature_columns.pkl')
        features_for_clustering = joblib.load('clustering_feature_cols.pkl')

        print(f"Feature clustering : {len(features_for_clustering)} kolom")
        print(f"Feature RF         : {len(rf_features)} kolom")

    except FileNotFoundError as e:
        print(f"ERROR: File .pkl tidak ditemukan. Detail: {str(e)}")
        db.close()
        return

    # ===========================================================================
    # 2. BACA DATA — CSV seed + user baru dari DB
    # ===========================================================================
    csv_df = pd.DataFrame()
    try:
        csv_df = pd.read_csv('single_customer_view.csv')
        print(f"CSV seed: {len(csv_df)} nasabah.")
    except FileNotFoundError:
        print("WARNING: CSV seed tidak ditemukan.")

    db_df = build_scv_from_db(db)
    print(f"DB: {len(db_df)} nasabah.")

    if not csv_df.empty and not db_df.empty:
        existing_ids = set(csv_df['user_id'].tolist())
        new_users_df = db_df[~db_df['user_id'].isin(existing_ids)]
        print(f"User baru dari DB: {len(new_users_df)}")
        scv_df = pd.concat([csv_df, new_users_df], ignore_index=True)
    elif not csv_df.empty:
        scv_df = csv_df
    elif not db_df.empty:
        scv_df = db_df
    else:
        print("ERROR: Tidak ada data untuk diproses.")
        db.close()
        return

    # ===========================================================================
    # 3. PASTIKAN SEMUA KOLOM ADA — isi 0 jika tidak ada
    # ===========================================================================
    all_needed = list(set(features_for_clustering + rf_features))
    for col in all_needed:
        if col not in scv_df.columns:
            scv_df[col] = 0
            print(f"INFO: Kolom '{col}' diisi 0.")
        scv_df[col] = pd.to_numeric(scv_df[col], errors='coerce').fillna(0)

    # ===========================================================================
    # 4. PREDIKSI
    # ===========================================================================
    X_scaled = scaler.transform(scv_df[features_for_clustering])
    clusters  = kmeans.predict(X_scaled)
    scv_df['cluster_id'] = clusters

    cta_encoded = rf_model.predict(scv_df[rf_features])
    cta_preds   = le_cta.inverse_transform(cta_encoded)
    scv_df['predicted_cta_batch'] = cta_preds

    proba = rf_model.predict_proba(scv_df[rf_features])
    scv_df['batch_confidence'] = proba.max(axis=1)

    print(f"Distribusi cluster:\n{scv_df['cluster_id'].value_counts().sort_index().to_string()}")

    # ===========================================================================
    # 5. SIMPAN KE DB
    # ===========================================================================
    has_generated_message = 'generated_message' in scv_df.columns

    fallback_map = {
        'Food & Beverage':           "Nikmati promo spesial di merchant favoritmu!",
        'E-Wallet':                  "Top-up e-wallet makin praktis. Dapatkan cashback khusus minggu ini!",
        'Transport & Mobility':      "Sering bepergian? Gunakan QRIS dan dapatkan diskonnya.",
        'Internet':                  "Tagihan internet terbayar tepat waktu? Pantau pengeluaran rutinmu.",
        'Utilities':                 "Kelola tagihan bulanan lebih mudah dengan fitur jadwal otomatis.",
        'Lifestyle & Entertainment': "Hiburan lancar, keuangan tetap aman. Cek promo bulan ini!",
        'Telco':                     "Koneksi stabil adalah kebutuhan. Jadwalkan pembelian paket datamu.",
        'Retail & Convenience':      "Belanja harian lebih hemat dengan promo merchant pilihan CIMB.",
    }

    success_count = 0
    skip_count    = 0
    error_count   = 0

    BATCH_SIZE = 100

    for idx, row in scv_df.iterrows():
        try:
            user_id       = int(row['user_id'])
            cluster_id    = int(row['cluster_id'])
            predicted_cta = str(row['predicted_cta_batch']).strip() or "Ambil Promo"
            fav_category  = str(row.get('fav_category', 'Retail & Convenience'))
            confidence    = float(row['batch_confidence'])

            raw = row.get('trigger_reason', '')
            trigger_reason = str(raw) if pd.notna(raw) and str(raw).strip() not in ('', 'nan') else None

            raw_msg = row.get('generated_message', '')
            if has_generated_message and str(raw_msg).strip() not in ('', 'nan', 'None'):
                msg = str(raw_msg).strip()
            else:
                msg = fallback_map.get(fav_category,
                    "Nikmati kemudahan transaksi harian dengan promo spesial CIMB.")

            if not db.query(models.Profile.user_id).filter(
                models.Profile.user_id == user_id
            ).first():
                skip_count += 1
                continue

            existing = db.query(models.ClusteringResult).filter(
                models.ClusteringResult.user_id == user_id
            ).first()

            if existing:
                existing.cluster_id                = cluster_id
                existing.predicted_cta             = predicted_cta
                existing.generated_message         = msg
                existing.category_focus            = fav_category
                existing.recommendation_confidence = confidence
                existing.trigger_reason            = trigger_reason
                existing.timestamp                 = datetime.now(timezone.utc)
            else:
                db.add(models.ClusteringResult(
                    user_id                   = user_id,
                    cluster_id                = cluster_id,
                    predicted_cta             = predicted_cta,
                    generated_message         = msg,
                    category_focus            = fav_category,
                    recommendation_confidence = confidence,
                    trigger_reason            = trigger_reason,
                    timestamp                 = datetime.now(timezone.utc)
                ))

            success_count += 1

            if success_count % BATCH_SIZE == 0:
                db.commit()
                print(f"  Commit: {success_count} user diproses...")

        except Exception as e:
            error_count += 1
            print(f"WARNING: user_id {row.get('user_id', '?')}: {str(e)}")
            continue

    db.commit()
    db.close()

    print("=" * 60)
    print("BATCH PREDICTION SELESAI")
    print(f"Berhasil : {success_count} | Skip : {skip_count} | Gagal : {error_count}")
    print("=" * 60)

# ============================================
# Auto triger untuk data per user
# ============================================
def run_single_user_prediction(user_id: int):
    db: Session = SessionLocal()
    try:
        scaler                  = joblib.load('scaler_clustering.pkl')
        kmeans                  = joblib.load('kmeans_model.pkl')
        rf_model                = joblib.load('rf_cta_model.pkl')
        le_cta                  = joblib.load('label_encoder_cta.pkl')
        rf_features             = joblib.load('feature_columns.pkl')
        features_for_clustering = joblib.load('clustering_feature_cols.pkl')
    except FileNotFoundError as e:
        print(f"ERROR pkl: {e}")
        db.close()
        return

    # 1. Buat SCV dari DB lalu filter khusus untuk user ini saja
    scv_df = build_scv_from_db(db)
    if scv_df.empty:
        print(f"User {user_id} belum memiliki transaksi apa pun.")
        db.close()
        return
        
    scv_df = scv_df[scv_df['user_id'] == user_id]
    if scv_df.empty:
        print(f"User {user_id} tidak ditemukan setelah ditarik dari DB.")
        db.close()
        return

    # 2. Isi kolom yang kurang dengan angka 0 (Mengatasi masalah NaN/Missing columns)
    all_needed = list(set(features_for_clustering + rf_features))
    for col in all_needed:
        if col not in scv_df.columns:
            scv_df[col] = 0
        scv_df[col] = pd.to_numeric(scv_df[col], errors='coerce').fillna(0)

    # 3. Proses Prediksi ML
    X_scaled  = scaler.transform(scv_df[features_for_clustering])
    cluster_id = int(kmeans.predict(X_scaled)[0])
    
    cta_encoded = rf_model.predict(scv_df[rf_features])
    predicted_cta = str(le_cta.inverse_transform(cta_encoded)[0]).strip() or "Ambil Promo"
    
    proba = rf_model.predict_proba(scv_df[rf_features])
    confidence = float(proba.max(axis=1)[0])
    
    # 4. Generate Pesan Rekomendasi (Fallback)
    fav_category = str(scv_df.iloc[0].get('fav_category', 'Retail & Convenience'))
    fallback_map = {
        'Food & Beverage':           "Nikmati promo spesial di merchant favoritmu!",
        'E-Wallet':                  "Top-up e-wallet makin praktis. Dapatkan cashback khusus minggu ini!",
        'Transport & Mobility':      "Sering bepergian? Gunakan QRIS dan dapatkan diskonnya.",
        'Internet':                  "Tagihan internet terbayar tepat waktu? Pantau pengeluaran rutinmu.",
        'Utilities':                 "Kelola tagihan bulananmu lebih mudah dengan fitur jadwal otomatis.",
        'Lifestyle & Entertainment': "Hiburan lancar, keuangan tetap aman. Cek promo bulan ini!",
        'Telco':                     "Koneksi stabil adalah kebutuhan. Jadwalkan pembelian paket datamu.",
        'Retail & Convenience':      "Belanja harian lebih hemat dengan promo merchant pilihan CIMB.",
    }
    msg = fallback_map.get(fav_category, "Nikmati kemudahan transaksi harian dengan promo spesial CIMB.")

    # 5. Simpan atau Update (Upsert) ke Tabel ClusteringResult
    existing = db.query(models.ClusteringResult).filter(
        models.ClusteringResult.user_id == user_id
    ).first()
    
    if existing:
        existing.cluster_id                = cluster_id
        existing.predicted_cta             = predicted_cta
        existing.generated_message         = msg
        existing.category_focus            = fav_category
        existing.recommendation_confidence = confidence
        existing.timestamp                 = datetime.now(timezone.utc)
    else:
        db.add(models.ClusteringResult(
            user_id=user_id, 
            cluster_id=cluster_id,
            predicted_cta=predicted_cta, 
            generated_message=msg,
            category_focus=fav_category,
            recommendation_confidence=confidence,
            timestamp=datetime.now(timezone.utc)
        ))
        
    db.commit()
    db.close()
    print(f"✅ Auto-trigger berhasil untuk user_id {user_id}: masuk Cluster {cluster_id}")

if __name__ == "__main__":
    run_batch_prediction()