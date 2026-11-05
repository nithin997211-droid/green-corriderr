"""
Queue Clearance Flush Time Predictor (Model A - Tabular LightGBM)
Mysuru Green Corridor Intelligent Traffic Management System (ITMS)
"""

import os
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

JUNCTIONS = ["J1_Ayurvedic", "J2_Irwin", "J3_KR_Hospital"]
PHASES = ["RED", "YELLOW", "GREEN"]

def generate_synthetic_traffic_data(n_samples: int = 12000, seed: int = 42) -> pd.DataFrame:
    """
    Generates realistic urban traffic data calibrated for Indian corridor conditions:
    - Junction bottlenecks (J2 Irwin Road market gridlock factor)
    - Heavy vehicle inertia (KSRTC buses, emergency approach queues)
    - Peak hour congestion surges
    - Signal phase start-up loss time
    """
    np.random.seed(seed)

    # 1. Junction selection (uniform with slight skew to J2)
    junction_probs = [0.30, 0.40, 0.30]
    junction_ids = np.random.choice(JUNCTIONS, size=n_samples, p=junction_probs)

    # 2. Time of day (0-23)
    hours = np.random.randint(0, 24, size=n_samples)

    # 3. Peak hour flag (08:00 - 11:00 & 17:00 - 20:30)
    is_peak = np.array([
        1 if (8 <= h <= 10 or 17 <= h <= 20) else 0 for h in hours
    ])

    # 4. Vehicle count queued at intersection (5 to 120)
    # Peak hours have significantly higher queue counts
    base_counts = np.random.gamma(shape=3.5, scale=8.0, size=n_samples)
    peak_multipliers = np.where(is_peak == 1, np.random.uniform(1.8, 2.5, size=n_samples), 1.0)
    vehicle_counts = np.clip(np.round(base_counts * peak_multipliers + 5), 5, 120).astype(int)

    # 5. Heavy vehicle ratio (0.0 to 0.4) representing city buses, freight, and auto-rickshaw clusters
    heavy_ratio = np.clip(np.random.beta(a=2.0, b=5.0, size=n_samples) * 0.45, 0.0, 0.40)

    # 6. Current signal phase
    phase_probs = [0.55, 0.10, 0.35]  # RED is most commonly encountered by queues
    phases = np.random.choice(PHASES, size=n_samples, p=phase_probs)

    # 7. Ground Truth Calculation: Nonlinear Flush Time (seconds)
    # Saturation flow rate & startup delay under Indian mixed-traffic conditions
    # Base headway: ~1.8s - 2.1s per passenger car equivalent
    # Heavy vehicles require 4.5s - 6.0s startup headway due to inertia
    junction_multipliers = {
        "J1_Ayurvedic": 1.08,
        "J2_Irwin": 1.28,       # Irwin Road bottleneck: narrow geometry + side friction
        "J3_KR_Hospital": 1.15   # Emergency gate turning conflict
    }

    startup_delays = {
        "RED": 3.2,     # Startup loss time from standing queue
        "YELLOW": 1.2,  # Drivers preparing or clearing
        "GREEN": 0.2    # Platoon already in motion
    }

    flush_times = []
    for j_id, count, h_ratio, peak, phase in zip(junction_ids, vehicle_counts, heavy_ratio, is_peak, phases):
        heavy_count = count * h_ratio
        light_count = count - heavy_count

        # Headway calculation
        light_time = light_count * 1.95
        heavy_time = heavy_count * 5.20

        # Bottleneck multiplier
        b_factor = junction_multipliers[j_id]

        # Queue compression non-linearity: dense queues clear progressively slower
        compression_penalty = 1.0 + (count / 240.0)

        # Peak hour friction factor
        friction = 1.12 if peak == 1 else 1.0

        # Startup loss
        startup = startup_delays[phase]

        # Raw flush time
        t_flush = (light_time + heavy_time) * b_factor * compression_penalty * friction + startup

        # Add Gaussian measurement/driver variance noise
        noise = np.random.normal(0, 1.4)
        t_final = max(3.5, round(t_flush + noise, 2))
        flush_times.append(t_final)

    df = pd.DataFrame({
        "junction_id": junction_ids,
        "vehicle_count": vehicle_counts,
        "heavy_vehicle_ratio": np.round(heavy_ratio, 3),
        "time_of_day_hour": hours,
        "is_peak_hour": is_peak,
        "current_signal_phase": phases,
        "flush_time_seconds": flush_times
    })

    return df

def train_and_export_model():
    print("[1/4] Generating realistic synthetic urban corridor dataset (12,000 samples)...")
    df = generate_synthetic_traffic_data(n_samples=12000, seed=42)

    features = [
        "junction_id",
        "vehicle_count",
        "heavy_vehicle_ratio",
        "time_of_day_hour",
        "is_peak_hour",
        "current_signal_phase"
    ]
    target = "flush_time_seconds"

    # Encode categoricals
    le_junction = LabelEncoder()
    le_phase = LabelEncoder()

    df_encoded = df.copy()
    df_encoded["junction_id"] = le_junction.fit_transform(df["junction_id"])
    df_encoded["current_signal_phase"] = le_phase.fit_transform(df["current_signal_phase"])

    X = df_encoded[features]
    y = df_encoded[target]

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.20, random_state=42)

    print("[2/4] Training LightGBM Regressor for Queue Flush Time Prediction...")
    model = lgb.LGBMRegressor(
        objective="regression",
        metric="rmse",
        n_estimators=600,
        learning_rate=0.04,
        num_leaves=31,
        max_depth=6,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        n_jobs=-1
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(stopping_rounds=40, verbose=False)]
    )

    # Evaluate
    val_preds = model.predict(X_val)
    rmse = np.sqrt(mean_squared_error(y_val, val_preds))
    mae = mean_absolute_error(y_val, val_preds)
    r2 = r2_score(y_val, val_preds)

    print("\n" + "=" * 60)
    print("  LIGHTGBM QUEUE FLUSH PREDICTOR - TRAINING RESULTS")
    print("=" * 60)
    print(f"  Validation RMSE : {rmse:.3f} seconds")
    print(f"  Validation MAE  : {mae:.3f} seconds")
    print(f"  Validation R^2  : {r2:.4f}")
    print("=" * 60)

    # 3. Export model & metadata
    pkl_path = os.path.join(MODEL_DIR, "queue_flush_lgbm.pkl")
    txt_path = os.path.join(MODEL_DIR, "queue_flush_lgbm.txt")
    meta_path = os.path.join(MODEL_DIR, "model_metadata.joblib")

    print(f"[3/4] Exporting model artifact to: {pkl_path}")
    joblib.dump(model, pkl_path)
    model.booster_.save_model(txt_path)

    metadata = {
        "features": features,
        "target": target,
        "junction_classes": list(le_junction.classes_),
        "phase_classes": list(le_phase.classes_),
        "rmse": float(rmse),
        "mae": float(mae),
        "r2": float(r2)
    }
    joblib.dump(metadata, meta_path)
    print(f"[4/4] Model metadata and encoders saved to: {meta_path}")
    print("[SUCCESS] LightGBM Model A ready for production inference.\n")

if __name__ == "__main__":
    train_and_export_model()
