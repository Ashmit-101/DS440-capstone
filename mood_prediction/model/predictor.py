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
from typing import Optional

import numpy as np
import pandas as pd

import config
from features.builder import SURVEY_FEATURE_COLS, build_daily_features
from processors.phq9 import load_phq9_scores

# Module-level cache so the model is only loaded once per process lifetime
_artifact_cache: dict | None = None
_survey_artifact_cache: dict | None = None

MANUAL_SURVEY_FIELDS: list[dict[str, str]] = [
    {
        "key": "mood_today",
        "label": "Mood Right Now",
        "description": "How are you feeling overall today?",
        "scale_low": "Very low",
        "scale_high": "Very good",
    },
    {
        "key": "energy_today",
        "label": "Energy",
        "description": "How much mental and physical energy did you have today?",
        "scale_low": "Drained",
        "scale_high": "Strong",
    },
    {
        "key": "stress_today",
        "label": "Stress",
        "description": "How heavy or stressful did today feel?",
        "scale_low": "Calm",
        "scale_high": "Overwhelming",
    },
    {
        "key": "sleep_quality",
        "label": "Sleep Quality",
        "description": "How restorative did your sleep feel?",
        "scale_low": "Very poor",
        "scale_high": "Very restorative",
    },
    {
        "key": "social_connection",
        "label": "Connection",
        "description": "How connected did you feel to other people today?",
        "scale_low": "Isolated",
        "scale_high": "Connected",
    },
]


def _load_cached_artifact(path: Path, cache_name: str, training_hint: str) -> dict:
    global _artifact_cache, _survey_artifact_cache
    cache = _artifact_cache if cache_name == "default" else _survey_artifact_cache
    if cache is None:
        if not path.exists():
            raise FileNotFoundError(training_hint)
        with open(path, "rb") as f:
            cache = pickle.load(f)
        if cache_name == "default":
            _artifact_cache = cache
        else:
            _survey_artifact_cache = cache
    return cache


def load_artifact() -> dict:
    return _load_cached_artifact(
        config.MODEL_PATH,
        "default",
        "Model has not been trained yet. POST /train first.",
    )


def load_survey_artifact() -> dict:
    return _load_cached_artifact(
        config.SURVEY_MODEL_PATH,
        "survey",
        "Survey model has not been trained yet. POST /train-survey first.",
    )


def invalidate_cache() -> None:
    """Call after re-training to force the next prediction to reload."""
    global _artifact_cache, _survey_artifact_cache
    _artifact_cache = None
    _survey_artifact_cache = None


def get_manual_survey_fields() -> list[dict[str, str]]:
    return MANUAL_SURVEY_FIELDS


def _clamp_likert(value: int) -> int:
    return max(1, min(5, int(value)))


def _sleep_quality_to_hours(sleep_quality: int) -> float:
    return {
        1: 4.5,
        2: 5.75,
        3: 6.75,
        4: 7.75,
        5: 8.75,
    }[_clamp_likert(sleep_quality)]


def load_health_data() -> pd.DataFrame:
    """Load mock Apple Health data from health_data.csv."""
    health_path = config.DATASET_ROOT.parent / "mood_prediction" / "health_data.csv"
    if health_path.exists():
        return pd.read_csv(health_path)
    return pd.DataFrame()


def get_today_health_data(user_id: str = "user_demo") -> dict:
    """Get today's health data for a user, or latest available if today not found."""
    health_df = load_health_data()
    if health_df.empty:
        return {}

    user_data = health_df[health_df["user_id"] == user_id].copy()
    if user_data.empty:
        return {}

    # Sort by date and get the most recent entry
    user_data["date"] = pd.to_datetime(user_data["date"])
    latest = user_data.sort_values("date").iloc[-1]
    record: dict[str, float | str | None] = {"date": str(latest["date"].date())}
    for key, value in latest.items():
        if key == "date":
            continue
        if pd.isna(value):
            record[key] = None
        elif key == "user_id":
            record[key] = str(value)
        else:
            record[key] = float(value)
    return record


def _sad_indicator(mood_today: int) -> int:
    mood_today = _clamp_likert(mood_today)
    if mood_today <= 2:
        return 2
    if mood_today == 3:
        return 1
    return 0


def _build_manual_feature_values(
    responses: dict[str, int],
    health_data: Optional[dict] = None,
) -> dict[str, float]:
    """Build feature values from survey responses + optional Apple Health data."""
    mood_today = _clamp_likert(responses["mood_today"])
    energy_today = _clamp_likert(responses["energy_today"])
    stress_today = _clamp_likert(responses["stress_today"])
    sleep_quality = _clamp_likert(responses["sleep_quality"])
    social_connection = _clamp_likert(responses["social_connection"])

    calmness = 6 - stress_today
    social_drain = 6 - social_connection

    def from_health(key: str) -> Optional[float]:
        if not health_data:
            return None
        value = health_data.get(key)
        if value is None:
            return None
        return float(value)

    # Use real health data if available, otherwise fall back to synthetic mapping
    if from_health("sleep_hours") is not None:
        sleep_hours = float(from_health("sleep_hours"))
    else:
        sleep_hours = _sleep_quality_to_hours(sleep_quality)

    if from_health("walk_amount") is not None:
        walk_amount = round(float(from_health("walk_amount")), 2)
    elif from_health("steps") is not None:
        steps = float(from_health("steps"))
        walk_amount = round(min(5, max(1, steps / 4000)), 2)
    else:
        walk_amount = round((energy_today + social_connection) / 2, 2)

    if from_health("activity_mean") is not None:
        activity_mean = round(float(from_health("activity_mean")), 6)
    elif from_health("steps") is not None:
        steps = float(from_health("steps"))
        activity_level = min(5, max(1, steps / 4000))  # 4k steps = 1, 20k steps = 5
        activity_mean = round(min(0.95, max(0.01, activity_level / 20)), 6)
    else:
        activity_mean = round(float(energy_today) / 20, 6)

    if from_health("activity_std") is not None:
        activity_std = round(float(from_health("activity_std")), 6)
    else:
        activity_std = round((stress_today + abs(mood_today - 3) + 1) / 10, 6)

    if from_health("activity_nonzero_frac") is not None:
        activity_nonzero_frac = round(float(from_health("activity_nonzero_frac")), 6)
    else:
        activity_nonzero_frac = round(
            min(0.5, max(0.01, activity_mean * 0.55)),
            6,
        )

    if from_health("exercise_intensity") is not None:
        exercise_intensity = round(float(from_health("exercise_intensity")), 2)
    elif from_health("calories_burned") is not None:
        calories = float(from_health("calories_burned"))
        exercise_intensity = min(5, max(1, (calories - 1000) / 400))  # scaled to 1-5
    else:
        exercise_intensity = round((energy_today + calmness) / 2, 2)

    phone_locked_duration = from_health("phone_locked_duration")
    if phone_locked_duration is None:
        phone_locked_duration = round((25000 + sleep_quality * 4500 + social_drain * 1800), 2)

    phone_lock_events = from_health("phone_lock_events")
    if phone_lock_events is None:
        phone_lock_events = round(max(1, min(9, 2 + stress_today)), 2)

    screen_off_duration = from_health("screen_off_duration")
    if screen_off_duration is None:
        screen_off_duration = round((18000 + sleep_quality * 6500 + calmness * 1800), 2)

    screen_off_events = from_health("screen_off_events")
    if screen_off_events is None:
        screen_off_events = round(max(1, min(7, 1 + sleep_quality)), 2)

    conversation_duration = from_health("conversation_duration")
    if conversation_duration is None:
        conversation_duration = round((5000 + social_connection * 4200 + energy_today * 1200), 2)

    conversation_count = from_health("conversation_count")
    if conversation_count is None:
        conversation_count = round(max(1, social_connection * 10 + energy_today * 4), 2)

    phq9_score = from_health("phq9_score")
    if phq9_score is None:
        phq9_score = round((stress_today + (6 - mood_today)) / 2, 2)

    feature_values = {
        "happy": float(mood_today),
        "sad": float(6 - mood_today),
        "sadornot": float(_sad_indicator(mood_today)),
        "sleep_hours": sleep_hours,
        "sleep_rate": float(sleep_quality),
        "stress_level": float(stress_today),
        "exercise_intensity": round(exercise_intensity, 2),
        "walk_amount": walk_amount,
        "activity_mean": activity_mean,
        "activity_std": activity_std,
        "activity_nonzero_frac": activity_nonzero_frac,
        "phone_locked_duration": phone_locked_duration,
        "phone_lock_events": phone_lock_events,
        "screen_off_duration": screen_off_duration,
        "screen_off_events": screen_off_events,
        "conversation_duration": conversation_duration,
        "conversation_count": conversation_count,
        "phq9_score": phq9_score,
    }

    feature_values.update(
        {
            "activity_mean_7d": feature_values["activity_mean"],
            "conversation_duration_7d": feature_values["conversation_duration"],
            "exercise_intensity_7d": feature_values["exercise_intensity"],
            "happy_7d": feature_values["happy"],
            "phone_locked_duration_7d": feature_values["phone_locked_duration"],
            "sad_7d": feature_values["sad"],
            "sleep_hours_7d": feature_values["sleep_hours"],
            "sleep_rate_7d": feature_values["sleep_rate"],
            "stress_level_7d": feature_values["stress_level"],
        }
    )

    return feature_values


def _build_manual_survey_feature_values(responses: dict[str, int]) -> dict[str, float]:
    mood_today = _clamp_likert(responses["mood_today"])
    stress_today = _clamp_likert(responses["stress_today"])
    sleep_quality = _clamp_likert(responses["sleep_quality"])
    energy_today = _clamp_likert(responses["energy_today"])
    social_connection = _clamp_likert(responses["social_connection"])

    feature_values = {
        "happy": float(mood_today),
        "sad": float(6 - mood_today),
        "sadornot": float(_sad_indicator(mood_today)),
        "stress_level": float(stress_today),
        "sleep_rate": float(sleep_quality),
        "energy": float(energy_today),
        "social": float(social_connection),
        "happy_7d": float(mood_today),
        "stress_level_7d": float(stress_today),
        "sleep_rate_7d": float(sleep_quality),
        "energy_7d": float(energy_today),
        "social_7d": float(social_connection),
    }
    return {col: feature_values[col] for col in SURVEY_FEATURE_COLS}


def _survey_signal_score(responses: dict[str, int]) -> float:
    mood_today = _clamp_likert(responses["mood_today"])
    stress_today = _clamp_likert(responses["stress_today"])
    sleep_quality = _clamp_likert(responses["sleep_quality"])
    energy_today = _clamp_likert(responses["energy_today"])
    social_connection = _clamp_likert(responses["social_connection"])

    # Blend the model output with a direct survey composite so every answer
    # remains behaviorally meaningful even when the learned surface is flat.
    return float(
        0.34 * mood_today
        + 0.16 * energy_today
        + 0.18 * (6 - stress_today)
        + 0.16 * sleep_quality
        + 0.16 * social_connection
    )


def _manual_descriptor_for_score(score: float) -> dict[str, float | str]:
    bucket_index = int(np.floor((float(np.clip(score, 1.0, 5.0)) - 1.0) / 0.3))
    bucket_index = max(0, min(13, bucket_index))

    low = round(1.0 + bucket_index * 0.3, 1)
    high = round(min(5.0, low + 0.3), 1)
    labels = [
        "Very Heavy",
        "Heavy",
        "Quite Low",
        "Low",
        "Fragile",
        "Mixed",
        "Slightly Mixed",
        "Steady",
        "Fairly Steady",
        "Encouraging",
        "Positive",
        "Strong",
        "Very Strong",
        "Excellent",
    ]

    return {
        "forecast_descriptor": labels[bucket_index],
        "forecast_range_low": low,
        "forecast_range_high": high,
        "forecast_range_label": f"{low:.1f}-{high:.1f}",
    }


def _build_manual_insight(responses: dict[str, int], predicted_score: float) -> tuple[str, list[str], str]:
    mood_today = _clamp_likert(responses["mood_today"])
    energy_today = _clamp_likert(responses["energy_today"])
    stress_today = _clamp_likert(responses["stress_today"])
    sleep_quality = _clamp_likert(responses["sleep_quality"])
    social_connection = _clamp_likert(responses["social_connection"])

    drivers: list[str] = []
    if sleep_quality <= 2:
        drivers.append("sleep looked like a drag today")
    elif sleep_quality >= 4:
        drivers.append("sleep is supporting you")

    if stress_today >= 4:
        drivers.append("stress is pulling the forecast down")
    elif stress_today <= 2:
        drivers.append("lower stress is helping stability")

    if social_connection >= 4:
        drivers.append("connection is giving you some lift")
    elif social_connection <= 2:
        drivers.append("low connection may be weighing on tomorrow")

    if energy_today >= 4:
        drivers.append("energy is a positive signal")
    elif energy_today <= 2:
        drivers.append("low energy makes tomorrow less steady")

    if not drivers:
        drivers.append("today looked fairly middle-of-the-road")

    if predicted_score >= mood_today + 0.4:
        summary = "Tomorrow looks a bit better than today."
    elif predicted_score <= mood_today - 0.4:
        summary = "Tomorrow may feel a bit heavier than today."
    else:
        summary = "Tomorrow looks fairly close to today."

    band = (
        "Low confidence. This is still an early behavioral estimate, not a clinical signal."
        if stress_today >= 4 and sleep_quality <= 2
        else "Moderate confidence. Treat this as a directional check-in, not a precise score."
    )

    return summary, drivers[:3], band


def predict_mood_from_survey(responses: dict[str, int]) -> dict:
    """
    Predict tomorrow's happy score from a short human-centered check-in.

    The manual check-in is translated into a survey-native feature space that
    does not depend on mock Apple Health rows or passive sensing overrides.
    """
    artifact = load_survey_artifact()
    pipeline = artifact["pipeline"]
    feature_cols: list[str] = artifact["feature_cols"]

    feature_values = _build_manual_survey_feature_values(responses)
    row = {col: feature_values.get(col, np.nan) for col in feature_cols}
    X = pd.DataFrame([row], columns=feature_cols).values

    raw_pred = float(pipeline.predict(X)[0])
    survey_signal = _survey_signal_score(responses)
    blended_pred = 0.4 * raw_pred + 0.6 * survey_signal
    predicted_score = round(float(np.clip(blended_pred, 1.0, 5.0)), 2)
    today = date.today()
    summary, likely_drivers, confidence_note = _build_manual_insight(
        responses, predicted_score
    )
    descriptor = _manual_descriptor_for_score(predicted_score)

    return {
        "features_from_date": str(today),
        "prediction_for_date": str((pd.Timestamp(today) + pd.Timedelta(days=1)).date()),
        "predicted_happy_score": predicted_score,
        "model_cv_mae": artifact.get("cv_mae"),
        "model_cv_std": artifact.get("cv_std"),
        "summary": summary,
        "likely_drivers": likely_drivers,
        "confidence_note": confidence_note,
        **descriptor,
    }


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
