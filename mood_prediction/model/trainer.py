"""
Model trainer: builds the full training dataset, fits a GradientBoosting
pipeline, cross-validates, and persists the artifact to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import pickle

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold, TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import config
from features.builder import (
    TARGET_COL,
    SURVEY_FEATURE_COLS,
    build_daily_features,
    build_training_dataset,
    get_feature_columns,
)

logger = logging.getLogger(__name__)


def _build_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.05,
                    subsample=0.8,
                    min_samples_leaf=15,
                    random_state=42,
                ),
            ),
        ]
    )


def get_all_user_ids() -> list[str]:
    """Discover all users that have Mood EMA data."""
    return sorted(
        p.stem.replace("Mood_", "")
        for p in config.MOOD_DIR.glob("Mood_u*.json")
    )


def _all_dataset_user_ids() -> set[str]:
    """Find every user that appears in *any* sensing or EMA directory."""
    users: set[str] = set()
    dirs = [
        config.MOOD_DIR, config.SLEEP_DIR, config.STRESS_DIR,
        config.EXERCISE_DIR, config.ACTIVITY_DIR, config.PHONELOCK_DIR,
        config.DARK_DIR, config.CONVERSATION_DIR,
    ]
    for d in dirs:
        if not d.exists():
            continue
        for p in d.glob("*_u*.json"):
            # filenames like Mood_u01.json, activity_u01.json, etc.
            stem = p.stem  # e.g. "Mood_u01" or "activity_u01"
            uid = stem.split("_")[-1]  # take last segment "u01"
            if uid.startswith("u"):
                users.add(uid)
    return users


def diagnose_users() -> dict:
    """
    Report dataset coverage across all users found in any data source.

    Logs:
    - Total unique users found across all sources
    - Users missing a Mood EMA file (can never contribute training rows)
    - Per-user mood-day counts for users with sparse data (< 5 days)
    - Sensor completeness summary for the worst LOUO-CV users
    """
    all_users = _all_dataset_user_ids()
    mood_users = set(get_all_user_ids())
    missing_mood = sorted(all_users - mood_users)

    logger.info(
        "Dataset coverage: %d total users across all sources, %d have Mood EMA files, "
        "%d have NO Mood EMA file: %s",
        len(all_users), len(mood_users), len(missing_mood), missing_mood,
    )

    sparse: dict[str, int] = {}
    for uid in sorted(mood_users):
        daily = build_daily_features(uid)
        n = len(daily)
        if n < 5:
            sparse[uid] = n

    if sparse:
        logger.info("Users with fewer than 5 mood days (likely excluded): %s", sparse)

    # Sensor completeness for known worst LOUO users
    problem_users = ["u47", "u32", "u00"]
    for uid in problem_users:
        if uid not in mood_users:
            continue
        daily = build_daily_features(uid)
        if daily.empty:
            logger.info("User %s: no daily data at all", uid)
            continue
        sensor_cols = [
            "sleep_hours", "stress_level", "conversation_duration",
            "activity_mean", "phone_locked_duration",
        ]
        present = {c: int(daily[c].notna().sum()) for c in sensor_cols if c in daily.columns}
        logger.info(
            "User %s: %d mood days, sensor non-null counts: %s",
            uid, len(daily), present,
        )

    return {"all_users": len(all_users), "mood_users": len(mood_users), "missing_mood": missing_mood}


def _normalized_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    series = pd.to_numeric(df[column], errors="coerce")
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=df.index, dtype=float)
    low = float(valid.quantile(0.05))
    high = float(valid.quantile(0.95))
    if high <= low:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return ((series - low) / (high - low)).clip(0.0, 1.0)


def _compose_likert_feature(components: list[pd.Series]) -> pd.Series:
    components_df = pd.concat(components, axis=1)
    score = 1.0 + 4.0 * components_df.mean(axis=1, skipna=True)
    score[components_df.notna().sum(axis=1) == 0] = np.nan
    return score.clip(1.0, 5.0)


def _impute_energy_social_features(dataset: pd.DataFrame) -> pd.DataFrame:
    energy = _compose_likert_feature(
        [
            _normalized_series(dataset, "exercise_intensity"),
            _normalized_series(dataset, "walk_amount"),
            _normalized_series(dataset, "activity_mean"),
            _normalized_series(dataset, "activity_nonzero_frac"),
        ]
    )
    social = _compose_likert_feature(
        [
            _normalized_series(dataset, "conversation_duration"),
            _normalized_series(dataset, "conversation_count"),
        ]
    )

    dataset = dataset.copy()
    dataset["energy"] = energy
    dataset["social"] = social

    energy_fallback = (
        0.35 * pd.to_numeric(dataset.get("happy"), errors="coerce")
        + 0.25 * (6 - pd.to_numeric(dataset.get("stress_level"), errors="coerce"))
        + 0.25 * pd.to_numeric(dataset.get("sleep_rate"), errors="coerce")
        + 0.15 * 3.0
    ).clip(1.0, 5.0)
    social_fallback = (
        0.45 * pd.to_numeric(dataset.get("happy"), errors="coerce")
        + 0.25 * (6 - pd.to_numeric(dataset.get("stress_level"), errors="coerce"))
        + 0.15 * pd.to_numeric(dataset.get("sleep_rate"), errors="coerce")
        + 0.15 * 3.0
    ).clip(1.0, 5.0)

    dataset["energy"] = dataset["energy"].fillna(energy_fallback)
    dataset["social"] = dataset["social"].fillna(social_fallback)
    return dataset


def build_survey_training_dataset(user_ids: list[str]) -> pd.DataFrame:
    all_rows: list[pd.DataFrame] = []

    for uid in user_ids:
        daily = build_daily_features(uid)
        if daily.empty or len(daily) < 3:
            continue

        daily = daily.sort_values("date").reset_index(drop=True)
        daily = _impute_energy_social_features(daily)

        for col in ["happy", "stress_level", "sleep_rate", "energy", "social"]:
            if col in daily.columns:
                daily[f"{col}_7d"] = daily[col].rolling(7, min_periods=1).mean()

        daily[TARGET_COL] = daily["happy"].shift(-1)
        daily = daily.dropna(subset=[TARGET_COL])
        all_rows.append(daily)

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True)


def _train_and_persist_model(
    dataset: pd.DataFrame,
    feature_cols: list[str],
    model_path: Path,
) -> dict:
    if dataset.empty:
        raise ValueError("No training data could be built from the dataset.")
    if not feature_cols:
        raise ValueError("No feature columns were available for training.")

    logger.info(
        "Training on %d samples, %d features, %d users",
        len(dataset),
        len(feature_cols),
        dataset["user_id"].nunique(),
    )

    X = dataset[feature_cols].values
    y = dataset[TARGET_COL].values.astype(float)

    pipeline = _build_pipeline()

    dataset_sorted = dataset.sort_values("date").reset_index(drop=True)
    X_sorted = dataset_sorted[feature_cols].values
    y_sorted = dataset_sorted[TARGET_COL].values.astype(float)

    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = cross_val_score(
        pipeline,
        X_sorted,
        y_sorted,
        cv=tscv,
        scoring="neg_mean_absolute_error",
    )
    cv_mae = float(-cv_scores.mean())
    cv_std = float(cv_scores.std())
    logger.info("CV MAE: %.3f ± %.3f (scale 1-5)", cv_mae, cv_std)

    pipeline.fit(X, y)
    y_pred_full = pipeline.predict(X)
    insample_mae = float(mean_absolute_error(y, y_pred_full))
    overfit_gap = cv_mae - insample_mae
    logger.info(
        "Overfitting check — in-sample MAE: %.3f | CV MAE: %.3f | gap: %.3f%s",
        insample_mae, cv_mae, overfit_gap,
        " (WARNING: gap > 0.3 suggests overfitting)" if overfit_gap > 0.3 else " (OK)",
    )

    low_mask = y <= 2
    high_mask = y > 2
    mae_low = float(mean_absolute_error(y[low_mask], y_pred_full[low_mask])) if low_mask.sum() > 0 else None
    mae_high = float(mean_absolute_error(y[high_mask], y_pred_full[high_mask])) if high_mask.sum() > 0 else None
    logger.info(
        "In-sample MAE — low (1-2): %s, high (3-5): %s",
        f"{mae_low:.3f}" if mae_low is not None else "n/a",
        f"{mae_high:.3f}" if mae_high is not None else "n/a",
    )

    r_value, _ = pearsonr(y, y_pred_full)
    logger.info("In-sample Pearson r: %.3f", r_value)

    perm_result = permutation_importance(
        pipeline,
        X,
        y,
        n_repeats=10,
        scoring="neg_mean_absolute_error",
        random_state=42,
        n_jobs=1,
    )
    perm_importances = {
        col: round(float(imp), 5)
        for col, imp in zip(feature_cols, perm_result.importances_mean)
    }
    top_features = sorted(perm_importances, key=perm_importances.get, reverse=True)[:10]
    logger.info("Top-10 permutation importances: %s", {k: perm_importances[k] for k in top_features})

    user_labels = dataset["user_id"].values
    unique_users = dataset["user_id"].unique()
    gkf = GroupKFold(n_splits=len(unique_users))
    per_user_mae: dict[str, float] = {}
    for train_idx, test_idx in gkf.split(X, y, groups=user_labels):
        uid = user_labels[test_idx[0]]
        pipe_clone = clone(pipeline)
        pipe_clone.fit(X[train_idx], y[train_idx])
        y_hat = pipe_clone.predict(X[test_idx])
        per_user_mae[uid] = round(float(mean_absolute_error(y[test_idx], y_hat)), 4)

    artifact = {
        "pipeline": pipeline,
        "feature_cols": feature_cols,
        "cv_mae": cv_mae,
        "cv_std": cv_std,
        "n_samples": int(len(dataset)),
        "n_users": int(dataset["user_id"].nunique()),
        "perm_importances": perm_importances,
        "per_user_mae": per_user_mae,
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(artifact, f)

    logger.info("Model saved to %s", model_path)

    return {
        "cv_mae": round(cv_mae, 4),
        "cv_std": round(cv_std, 4),
        "insample_mae": round(insample_mae, 4),
        "overfit_gap": round(overfit_gap, 4),
        "pearson_r": round(float(r_value), 4),
        "mae_low_1_2": round(mae_low, 4) if mae_low is not None else None,
        "mae_high_3_5": round(mae_high, 4) if mae_high is not None else None,
        "n_samples": artifact["n_samples"],
        "n_users": artifact["n_users"],
        "features": feature_cols,
        "perm_importances": perm_importances,
        "per_user_mae": per_user_mae,
    }


def train_model() -> dict:
    """
    Train and persist the mood prediction model.

    Returns a summary dict with CV metrics, sample counts, and feature list.
    """
    user_ids = get_all_user_ids()
    logger.info("Discovered %d users with Mood EMA data", len(user_ids))
    diagnose_users()

    dataset = build_training_dataset(user_ids)
    feature_cols = get_feature_columns(dataset)
    return _train_and_persist_model(dataset, feature_cols, config.MODEL_PATH)


def train_survey_model() -> dict:
    user_ids = get_all_user_ids()
    logger.info("Discovered %d users with Mood EMA data for survey model", len(user_ids))
    diagnose_users()

    dataset = build_survey_training_dataset(user_ids)
    feature_cols = [col for col in SURVEY_FEATURE_COLS if col in dataset.columns]
    return _train_and_persist_model(dataset, feature_cols, config.SURVEY_MODEL_PATH)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = train_model()
    print(result)
