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
        models.Profile.age,
        func.count(models.Transaction.trx_id).label('total_trx'),
        func.sum(models.Transaction.amount).label('total_spending'),
    ).join(
        models.Transaction, models.Profile.user_id == models.Transaction.user_id
    ).group_by(
        models.Profile.user_id,
        models.Profile.occupation,
        models.Profile.monthly_income,
        models.Profile.age,
    ).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([r._asdict() for r in rows])

    fav_cat_rows = db.query(
        models.Transaction.user_id,
        models.Transaction.category,
        func.count(models.Transaction.trx_id).label('cnt')
    ).group_by(
        models.Transaction.user_id,
        models.Transaction.category
    ).all()

    fav_df = pd.DataFrame([r._asdict() for r in fav_cat_rows])
    if not fav_df.empty:
        fav_df = fav_df.sort_values('cnt', ascending=False).drop_duplicates('user_id')
        fav_df = fav_df.rename(columns={'category': 'fav_category'})[['user_id', 'fav_category']]
        df = df.merge(fav_df, on='user_id', how='left')
        df['fav_category'] = df['fav_category'].fillna('Retail & Convenience')
    else:
        df['fav_category'] = 'Retail & Convenience'

    return df


def run_batch_prediction():
    print("Memulai pipeline batch prediction ML...")
    db: Session = SessionLocal()

    # ===========================================================================
    # 1. LOAD ML ARTIFACTS (.pkl)
    # ===========================================================================
    try:
        scaler                  = joblib.load('scaler_clustering.pkl')
        kmeans                  = joblib.load('kmeans_model.pkl')
        rf_model                = joblib.load('rf_cta_model.pkl')
        le_cta                  = joblib.load('label_encoder_cta.pkl')
        rf_features             = joblib.load('feature_columns.pkl')
        features_for_clustering = joblib.load('clustering_feature_cols.pkl')

        print("Berhasil memuat semua model ML dan feature list.")
        print(f"  Feature clustering : {len(features_for_clustering)} kolom")
        print(f"  Feature RF         : {len(rf_features)} kolom")

    except FileNotFoundError as e:
        print(f"ERROR: File .pkl tidak ditemukan. Detail: {str(e)}")
        db.close()
        return

    # ===========================================================================
    # 2. BACA DATA NASABAH — CSV (seed) + DB (user baru API)
    # ===========================================================================
    csv_df = pd.DataFrame()
    try:
        csv_df = pd.read_csv('single_customer_view_enriched.csv')
        print(f"Berhasil membaca {len(csv_df)} nasabah dari CSV seed.")
    except FileNotFoundError:
        print("WARNING: CSV seed tidak ditemukan, hanya proses user dari DB.")

    db_df = build_scv_from_db(db)
    if not db_df.empty:
        print(f"Berhasil membaca {len(db_df)} nasabah dari DB.")

    if not csv_df.empty and not db_df.empty:
        existing_ids = set(csv_df['user_id'].tolist())
        new_users_df = db_df[~db_df['user_id'].isin(existing_ids)]
        scv_df = pd.concat([csv_df, new_users_df], ignore_index=True)
        print(f"Total: {len(scv_df)} nasabah ({len(new_users_df)} user baru dari DB).")
    elif not csv_df.empty:
        scv_df = csv_df
    elif not db_df.empty:
        scv_df = db_df
    else:
        print("ERROR: Tidak ada data nasabah untuk diproses.")
        db.close()
        return

    # ===========================================================================
    # 3. VALIDASI KOLOM + ISI NaN
    # ===========================================================================
    missing_clustering = [c for c in features_for_clustering if c not in scv_df.columns]
    missing_rf         = [c for c in rf_features if c not in scv_df.columns]

    # Tambahkan kolom yang hilang dengan nilai 0
    for col in missing_clustering + missing_rf:
        if col not in scv_df.columns:
            scv_df[col] = 0
            print(f"INFO: Kolom '{col}' tidak ditemukan, diisi 0.")

    # Isi NaN yang tersisa dengan median (numerik) atau 0
    for col in features_for_clustering + rf_features:
        if scv_df[col].isnull().any():
            if scv_df[col].dtype in ['float64', 'int64']:
                scv_df[col] = scv_df[col].fillna(scv_df[col].median())
            else:
                scv_df[col] = scv_df[col].fillna(0)

    # ===========================================================================
    # 4. PREDIKSI CLUSTER (K-MEANS) & CTA (RANDOM FOREST)
    # ===========================================================================
    X_scaled = scaler.transform(scv_df[features_for_clustering])
    clusters = kmeans.predict(X_scaled)
    scv_df['cluster_id'] = clusters

    cta_encoded_preds = rf_model.predict(scv_df[rf_features])
    cta_preds = le_cta.inverse_transform(cta_encoded_preds)
    scv_df['predicted_cta_batch'] = cta_preds

    proba = rf_model.predict_proba(scv_df[rf_features])
    scv_df['batch_confidence'] = proba.max(axis=1)

    print(f"Prediksi selesai. Distribusi cluster:")
    print(scv_df['cluster_id'].value_counts().sort_index().to_string())

    # ===========================================================================
    # 5. SIMPAN KE DATABASE (Tabel ClusteringResult)
    # ===========================================================================
    print("Menyimpan hasil prediksi ke database...")

    has_generated_message = 'generated_message' in scv_df.columns
    success_count = 0
    skip_count    = 0
    error_count   = 0

    fallback_map = {
        'Food & Beverage':           "Nikmati promo spesial di merchant favoritmu!",
        'E-Wallet':                  "Top-up e-wallet makin praktis. Dapatkan cashback khusus minggu ini!",
        'Transport & Mobility':      "Sering bepergian? Gunakan QRIS untuk bayar transportasi dan dapatkan diskonnya.",
        'Internet':                  "Tagihan internet terbayar tepat waktu? Yuk, pantau pengeluaran rutinmu.",
        'Utilities':                 "Kelola tagihan bulananmu lebih mudah dengan fitur jadwal otomatis.",
        'Lifestyle & Entertainment': "Hiburan lancar, keuangan tetap aman. Cek promo spesial bulan ini!",
        'Telco':                     "Koneksi stabil adalah kebutuhan. Jadwalkan pembelian paket datamu otomatis.",
        'Retail & Convenience':      "Belanja harian lebih hemat dengan promo merchant pilihan CIMB.",
    }

    for idx, row in scv_df.iterrows():
        try:
            user_id       = int(row['user_id'])
            cluster_id    = int(row['cluster_id'])
            predicted_cta = str(row['predicted_cta_batch'])
            fav_category  = str(row['fav_category'])
            confidence    = float(row['batch_confidence'])

            raw = row.get('trigger_reason', '')
            trigger_reason = str(raw) if pd.notna(raw) and str(raw).strip() not in ('', 'nan') else None

            raw_msg = row.get('generated_message', '')
            if has_generated_message and str(raw_msg).strip() not in ('', 'nan', 'None'):
                msg = str(raw_msg).strip()
            else:
                msg = fallback_map.get(
                    fav_category,
                    "Nikmati kemudahan transaksi harian dengan promo spesial pilihan CIMB untuk Anda."
                )

            predicted_cta = predicted_cta.strip() or "Ambil Promo"

            profile_exists = db.query(models.Profile.user_id).filter(
                models.Profile.user_id == user_id
            ).first()
            if not profile_exists:
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

        except Exception as e:
            error_count += 1
            print(f"WARNING: Gagal memproses user_id {row.get('user_id', '?')}: {str(e)}")
            continue

    db.commit()
    db.close()

    print("=" * 60)
    print("BATCH PREDICTION SELESAI")
    print("=" * 60)
    print(f"Berhasil diproses : {success_count} user")
    print(f"Di-skip (no FK)   : {skip_count} user")
    print(f"Gagal             : {error_count} user")


if __name__ == "__main__":
    run_batch_prediction()