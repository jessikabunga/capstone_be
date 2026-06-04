import json
import pandas as pd
import joblib
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from datetime import datetime, timezone


def run_batch_prediction():
    print("Memulai pipeline batch prediction ML...")
    db: Session = SessionLocal()

    # ===========================================================================
    # 1. LOAD ML ARTIFACTS (.pkl)
    # ===========================================================================
    try:
        scaler   = joblib.load('scaler_clustering.pkl')
        kmeans   = joblib.load('kmeans_model.pkl')
        rf_model = joblib.load('rf_cta_model.pkl')
        le_cta   = joblib.load('label_encoder_cta.pkl')
        print("Berhasil memuat model ML.")
    except FileNotFoundError as e:
        print(f"ERROR: File model .pkl tidak ditemukan. Detail: {str(e)}")
        db.close()
        return

    # ===========================================================================
    # 2. LOAD FEATURE COLUMN LISTS (diekspor dari notebook ML)
    #    FIX: feature list wajib identik dengan yang dipakai saat training,
    #    bukan di-hardcode ulang di sini agar tidak mismatch.
    # ===========================================================================
    try:
        with open('clustering_feature_cols.json', 'r') as f:
            features_for_clustering = json.load(f)

        with open('rf_feature_cols.json', 'r') as f:
            rf_features = json.load(f)

        print(f"Feature clustering : {len(features_for_clustering)} kolom")
        print(f"Feature RF         : {len(rf_features)} kolom")
    except FileNotFoundError as e:
        print(f"ERROR: File feature list .json tidak ditemukan. Detail: {str(e)}")
        print("Pastikan notebook ML sudah mengekspor clustering_feature_cols.json dan rf_feature_cols.json.")
        db.close()
        return

    # ===========================================================================
    # 3. BACA DATA NASABAH
    # ===========================================================================
    try:
        scv_df = pd.read_csv('single_customer_view.csv')
        print(f"Berhasil membaca data {len(scv_df)} nasabah dari CSV.")
    except FileNotFoundError:
        print("ERROR: file single_customer_view.csv tidak ditemukan.")
        db.close()
        return

    # ===========================================================================
    # 4. VALIDASI KOLOM — pastikan semua kolom yang dibutuhkan tersedia
    #    FIX: fail-fast dengan pesan jelas, bukan KeyError di tengah loop.
    # ===========================================================================
    missing_clustering = [c for c in features_for_clustering if c not in scv_df.columns]
    missing_rf         = [c for c in rf_features if c not in scv_df.columns]

    if missing_clustering:
        print(f"ERROR: Kolom clustering tidak ditemukan di CSV: {missing_clustering}")
        db.close()
        return

    if missing_rf:
        print(f"ERROR: Kolom RF tidak ditemukan di CSV: {missing_rf}")
        db.close()
        return

    # ===========================================================================
    # 5. PREDIKSI CLUSTER (K-MEANS) & CTA (RANDOM FOREST)
    # ===========================================================================

    # Prediksi Cluster
    X_scaled = scaler.transform(scv_df[features_for_clustering])
    clusters = kmeans.predict(X_scaled)
    scv_df['cluster_id'] = clusters

    # Prediksi CTA
    cta_encoded_preds = rf_model.predict(scv_df[rf_features])
    cta_preds = le_cta.inverse_transform(cta_encoded_preds)
    scv_df['predicted_cta_batch'] = cta_preds

    # Confidence Score
    # FIX: gunakan proba aktual dari model, bukan konstanta 0.95.
    proba = rf_model.predict_proba(scv_df[rf_features])
    scv_df['batch_confidence'] = proba.max(axis=1)

    print(f"Prediksi selesai. Distribusi cluster:\n{scv_df['cluster_id'].value_counts().sort_index()}")

    # ===========================================================================
    # 6. SIMPAN HASIL KE DATABASE POSTGRESQL (Tabel ClusteringResult)
    #    FIX: gunakan generated_message dari Rule Engine (kolom 'generated_message'
    #    di SCV), bukan pesan statis yang di-hardcode di sini. Jika kolom belum ada
    #    (Rule Engine belum dijalankan), fallback ke pesan generik per kategori.
    # ===========================================================================
    print("Menyimpan hasil prediksi ke database...")

    has_generated_message = 'generated_message' in scv_df.columns

    success_count = 0
    error_count   = 0

    for idx, row in scv_df.iterrows():
        try:
            user_id      = int(row['user_id'])
            cluster_id   = int(row['cluster_id'])
            predicted_cta = str(row['predicted_cta_batch'])
            fav_category  = str(row['fav_category'])
            confidence    = float(row['batch_confidence'])

            # Ambil pesan dari Rule Engine jika tersedia, fallback jika tidak.
            if has_generated_message and str(row['generated_message']).strip():
                msg = str(row['generated_message'])
            else:
                fav = fav_category
                if fav == 'Food & Beverage':
                    msg = f"Halo {row['full_name']}, nikmati promo spesial di merchant favoritmu!"
                elif fav == 'E-Wallet':
                    msg = "Top-up e-wallet makin praktis. Dapatkan cashback khusus minggu ini!"
                elif fav == 'Transport & Mobility':
                    msg = "Sering bepergian? Gunakan QRIS untuk bayar transportasi dan dapatkan diskonnya."
                elif fav == 'Internet':
                    msg = "Tagihan internet terbayar tepat waktu? Yuk, pantau pengeluaran rutinmu."
                elif fav == 'Utilities':
                    msg = "Kelola tagihan bulananmu lebih mudah dengan fitur jadwal otomatis."
                elif fav == 'Lifestyle & Entertainment':
                    msg = "Hiburan lancar, keuangan tetap aman. Cek promo spesial bulan ini!"
                elif fav == 'Telco':
                    msg = "Koneksi stabil adalah kebutuhan. Jadwalkan pembelian paket datamu otomatis."
                else:
                    msg = "Nikmati kemudahan transaksi harian dengan promo spesial pilihan CIMB untuk Anda."

            # Upsert ke tabel ClusteringResult
            existing = db.query(models.ClusteringResult).filter(
                models.ClusteringResult.user_id == user_id
            ).first()

            if existing:
                existing.cluster_id               = cluster_id
                existing.predicted_cta            = predicted_cta
                existing.generated_message        = msg
                existing.category_focus           = fav_category
                existing.recommendation_confidence = confidence
                existing.timestamp                = datetime.now(timezone.utc)
            else:
                new_res = models.ClusteringResult(
                    user_id                   = user_id,
                    cluster_id                = cluster_id,
                    predicted_cta             = predicted_cta,
                    generated_message         = msg,
                    category_focus            = fav_category,
                    recommendation_confidence = confidence,
                    timestamp                 = datetime.now(timezone.utc)
                )
                db.add(new_res)

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
    print(f"Gagal             : {error_count} user")


if __name__ == "__main__":
    run_batch_prediction()