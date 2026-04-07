"""
Predictor: loads the trained model artifact and runs inference for a given
user and calendar date.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pickle
from datetime import date

import numpy as np
import pandas as pd

import config
from features.builder import build_daily_features, FEATURE_COLS
from processors.phq9 import load_phq9_scores

# Module-level cache so the model is only loaded once per process lifetime
_artifact_cache: dict | None = None


def load_artifact() -> dict:
    global _artifact_cache
    if _artifact_cache is None:
        if not config.MODEL_PATH.exists():
            raise FileNotFoundError(
                "Model has not been trained yet. POST /train first."
            )
        with open(config.MODEL_PATH, "rb") as f:
            _artifact_cache = pickle.load(f)
    return _artifact_cache


def invalidate_cache() -> None:
    """Call after re-training to force the next prediction to reload."""
    global _artifact_cache
    _artifact_cache = None


def predict_mood(user_id: str, query_date: date | None = None) -> dict:
    """
    Predict tomorrow's happy score for *user_id* using features from *query_date*.

    If *query_date* is None or has no data, the most recent available day is used.

    Returns a dict with:
        user_id, features_from_date, prediction_for_date, predicted_happy_score
    """
    artifact = load_artifact()
    pipeline = artifact["pipeline"]
    feature_cols: list[str] = artifact["feature_cols"]

    # ── Build daily features for the user ──────────────────────────────────────
    daily = build_daily_features(user_id)
    if daily.empty:
        raise ValueError(f"No data found for user '{user_id}'.")

    daily = daily.sort_values("date").reset_index(drop=True)

    # ── Select the target row ──────────────────────────────────────────────────
    if query_date is not None:
        row_df = daily[daily["date"] == query_date]
        if row_df.empty:
            # Fallback: nearest past day
            past = daily[daily["date"] <= query_date]
            row_df = past.tail(1) if not past.empty else daily.tail(1)
    else:
        row_df = daily.tail(1)

    row_df = row_df.copy()
    features_from_date = row_df["date"].values[0]

    # The predicted date is the day after the feature date
    prediction_for_date = pd.Timestamp(features_from_date) + pd.Timedelta(days=1)

    # ── Attach PHQ-9 baseline ──────────────────────────────────────────────────
    phq9 = load_phq9_scores(config.PHQ9_PATH)
    if not phq9.empty:
        score_vals = phq9[phq9["user_id"] == user_id]["phq9_score"].values
        row_df["phq9_score"] = score_vals[0] if len(score_vals) > 0 else np.nan

    # ── Build feature vector ───────────────────────────────────────────────────
    # Add any missing columns as NaN so the pipeline's imputer handles them
    for col in feature_cols:
        if col not in row_df.columns:
            row_df[col] = np.nan

    X = row_df[feature_cols].values  # shape (1, n_features)

    # ── Inference ─────────────────────────────────────────────────────────────
    raw_pred = float(pipeline.predict(X)[0])
    # Clamp to valid happy scale 1–5
    predicted_score = round(float(np.clip(raw_pred, 1.0, 5.0)), 2)

    return {
        "user_id": user_id,
        "features_from_date": str(features_from_date),
        "prediction_for_date": str(prediction_for_date.date()),
        "predicted_happy_score": predicted_score,
    }
