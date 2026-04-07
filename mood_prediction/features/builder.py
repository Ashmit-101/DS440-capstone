"""
Feature builder: combines all data sources into daily feature rows per user,
then creates (features_today → happy_tomorrow) training pairs.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this module directly from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from typing import List

import config
from processors.mood import load_mood_ema
from processors.sleep import load_sleep_features
from processors.stress import load_stress_features
from processors.exercise import load_exercise_features
from processors.activity import load_activity_features
from processors.phonelock import load_phonelock_features
from processors.dark import load_dark_features
from processors.conversation import load_conversation_features
from processors.phq9 import load_phq9_scores


# ── Feature column definitions ───────────────────────────────────────────────

FEATURE_COLS: List[str] = [
    # Today's mood (strong autoregressive signal)
    "happy",
    "sad",
    "happyornot",
    "sadornot",
    # Self-reported sleep
    "sleep_hours",
    "sleep_rate",
    # Self-reported stress
    "stress_level",
    # Self-reported exercise
    "exercise_intensity",
    "exercise_done",
    "walk_amount",
    # Passive activity sensing
    "activity_mean",
    "activity_std",
    "activity_nonzero_frac",
    # Phone usage proxy
    "phone_locked_duration",
    "phone_lock_events",
    # Screen usage
    "screen_off_duration",
    "screen_off_events",
    # Social interaction proxy
    "conversation_duration",
    "conversation_count",
    # Baseline depression (static per user)
    "phq9_score",
]

TARGET_COL = "happy_tomorrow"

# Columns for which 7-day rolling means are computed per user
ROLLING_BASE_COLS: List[str] = [
    "happy", "sad", "sleep_hours", "sleep_rate",
    "stress_level", "exercise_intensity", "activity_mean",
    "phone_locked_duration", "conversation_duration",
]


# ── Per-user daily feature matrix ─────────────────────────────────────────────

def build_daily_features(user_id: str) -> pd.DataFrame:
    """
    Build a daily feature DataFrame for a single user.

    Returns columns: user_id, date, <all feature cols>
    Each row = one calendar day where the user recorded mood.
    """
    mood = load_mood_ema(user_id, config.MOOD_DIR)
    if mood.empty:
        return pd.DataFrame()

    sources = [
        load_sleep_features(user_id, config.SLEEP_DIR),
        load_stress_features(user_id, config.STRESS_DIR),
        load_exercise_features(user_id, config.EXERCISE_DIR),
        load_activity_features(user_id, config.ACTIVITY_DIR),
        load_phonelock_features(user_id, config.PHONELOCK_DIR),
        load_dark_features(user_id, config.DARK_DIR),
        load_conversation_features(user_id, config.CONVERSATION_DIR),
    ]

    df = mood.copy()
    for src in sources:
        if src.empty:
            continue
        # Ensure user_id column exists (processors always set it)
        merge_on = ["user_id", "date"] if "user_id" in src.columns else ["date"]
        df = df.merge(src, on=merge_on, how="left")

    return df


# ── Full training dataset ──────────────────────────────────────────────────────

def build_training_dataset(user_ids: List[str]) -> pd.DataFrame:
    """
    Build the full (X, y) training table across all users.

    Each row: features from day T  →  target = happy score on day T+1.
    Also merges the static PHQ-9 baseline per user.
    Rolling 7-day means are added per user before creating training pairs.
    """
    import logging
    log = logging.getLogger(__name__)

    phq9 = load_phq9_scores(config.PHQ9_PATH)

    all_rows: List[pd.DataFrame] = []
    for uid in user_ids:
        daily = build_daily_features(uid)
        if daily.empty:
            log.debug("User %s skipped: no Mood EMA rows at all", uid)
            continue
        if len(daily) < 2:
            log.debug(
                "User %s skipped: only %d mood day(s) — need ≥2 to form a training pair",
                uid, len(daily),
            )
            continue

        daily = daily.sort_values("date").reset_index(drop=True)

        # Add 7-day rolling means for key sensor/EMA columns
        for col in ROLLING_BASE_COLS:
            if col in daily.columns:
                daily[f"{col}_7d"] = (
                    daily[col].rolling(7, min_periods=1).mean()
                )

        # Shift happy score back by one day to create the target
        daily[TARGET_COL] = daily["happy"].shift(-1)

        # Drop the last row (no next-day label) and rows missing the target
        daily = daily.dropna(subset=[TARGET_COL])

        log.debug("User %s contributed %d training rows", uid, len(daily))
        all_rows.append(daily)

    if not all_rows:
        return pd.DataFrame()

    dataset = pd.concat(all_rows, ignore_index=True)

    # Attach PHQ-9 baseline (left join — NaN if user has no survey data)
    if not phq9.empty:
        dataset = dataset.merge(phq9, on="user_id", how="left")

    return dataset


def get_feature_columns(dataset: pd.DataFrame | None = None) -> List[str]:
    """
    Return the feature columns that are present in dataset (or all defined ones).
    Includes static FEATURE_COLS plus any rolling _7d columns generated at
    training time. Always excludes the target and metadata columns.
    """
    if dataset is None:
        return FEATURE_COLS
    base = [c for c in FEATURE_COLS if c in dataset.columns]
    rolling = sorted(c for c in dataset.columns if c.endswith("_7d"))
    return base + rolling
