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
    build_training_dataset,
    get_feature_columns,
)

logger = logging.getLogger(__name__)


def get_all_user_ids() -> list[str]:
    """Discover all users that have Mood EMA data."""
    return sorted(
        p.stem.replace("Mood_", "")
        for p in config.MOOD_DIR.glob("Mood_u*.json")
    )


def train_model() -> dict:
    """
    Train and persist the mood prediction model.

    Returns a summary dict with CV metrics, sample counts, and feature list.
    """
    user_ids = get_all_user_ids()
    logger.info("Discovered %d users with Mood EMA data", len(user_ids))

    dataset = build_training_dataset(user_ids)
    if dataset.empty:
        raise ValueError("No training data could be built from the dataset.")

    feature_cols = get_feature_columns(dataset)
    logger.info(
        "Training on %d samples, %d features, %d users",
        len(dataset),
        len(feature_cols),
        dataset["user_id"].nunique(),
    )

    X = dataset[feature_cols].values
    y = dataset[TARGET_COL].values.astype(float)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    pipeline = Pipeline(
        [
            # Median imputation for missing sensor/EMA days
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                GradientBoostingRegressor(
                    n_estimators=100,   # reduced from 300 to curb overfitting
                    max_depth=3,        # reduced from 4
                    learning_rate=0.05,
                    subsample=0.8,
                    min_samples_leaf=15,  # increased from 5 — smoother trees
                    random_state=42,
                ),
            ),
        ]
    )

    # ── Cross-validation (time-series aware) ──────────────────────────────────
    # Sort by date within the dataset so the split respects temporal order
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

    # ── Fit on full dataset ────────────────────────────────────────────────────
    pipeline.fit(X, y)

    # ── 8.3 Per-class MAE (happy scores 1-2 vs 3-5) ──────────────────────────
    y_pred_full = pipeline.predict(X)
    low_mask = y <= 2
    high_mask = y > 2
    mae_low = float(mean_absolute_error(y[low_mask], y_pred_full[low_mask])) if low_mask.sum() > 0 else None
    mae_high = float(mean_absolute_error(y[high_mask], y_pred_full[high_mask])) if high_mask.sum() > 0 else None
    logger.info(
        "In-sample MAE — low (1-2): %s, high (3-5): %s",
        f"{mae_low:.3f}" if mae_low is not None else "n/a",
        f"{mae_high:.3f}" if mae_high is not None else "n/a",
    )

    # ── 8.4a Pearson r between predicted and actual ───────────────────────────
    r_value, _ = pearsonr(y, y_pred_full)
    logger.info("In-sample Pearson r: %.3f", r_value)

    # ── 8.4b Permutation importance ───────────────────────────────────────────
    perm_result = permutation_importance(
        pipeline, X, y,
        n_repeats=10,
        scoring="neg_mean_absolute_error",
        random_state=42,
        n_jobs=-1,
    )
    perm_importances = {
        col: round(float(imp), 5)
        for col, imp in zip(feature_cols, perm_result.importances_mean)
    }
    top_features = sorted(perm_importances, key=perm_importances.get, reverse=True)[:10]
    logger.info("Top-10 permutation importances: %s", {k: perm_importances[k] for k in top_features})

    # ── 8.4c Per-user leave-one-user-out CV ──────────────────────────────────
    user_labels = dataset["user_id"].values
    unique_users = dataset["user_id"].unique()
    n_users = len(unique_users)
    gkf = GroupKFold(n_splits=n_users)
    per_user_mae: dict[str, float] = {}
    for train_idx, test_idx in gkf.split(X, y, groups=user_labels):
        uid = user_labels[test_idx[0]]
        pipe_clone = clone(pipeline)
        pipe_clone.fit(X[train_idx], y[train_idx])
        y_hat = pipe_clone.predict(X[test_idx])
        per_user_mae[uid] = round(float(mean_absolute_error(y[test_idx], y_hat)), 4)
    worst_users = sorted(per_user_mae, key=per_user_mae.get, reverse=True)[:5]
    logger.info(
        "Per-user LOUO-CV MAE (worst 5): %s",
        {u: per_user_mae[u] for u in worst_users},
    )

    # ── Persist artifact ──────────────────────────────────────────────────────
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
    config.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.MODEL_PATH, "wb") as f:
        pickle.dump(artifact, f)

    logger.info("Model saved to %s", config.MODEL_PATH)

    return {
        "cv_mae": round(cv_mae, 4),
        "cv_std": round(cv_std, 4),
        "pearson_r": round(r_value, 4),
        "mae_low_1_2": round(mae_low, 4) if mae_low is not None else None,
        "mae_high_3_5": round(mae_high, 4) if mae_high is not None else None,
        "n_samples": artifact["n_samples"],
        "n_users": artifact["n_users"],
        "features": feature_cols,
        "perm_importances": perm_importances,
        "per_user_mae": per_user_mae,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = train_model()
    print(result)
