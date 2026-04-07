"""
FastAPI application for mood prediction.

Endpoints
---------
GET  /health            — liveness check + model status
POST /train             — train (or retrain) the model synchronously
POST /predict           — predict tomorrow's happy score for a user
GET  /predict/{user_id} — predict using most recent data (convenience GET)
GET  /model/info        — metadata about the currently loaded model
"""

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

# Make project root importable when the app is run from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

import config
from model.trainer import train_model
from model.predictor import invalidate_cache, load_artifact, predict_mood

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mood Prediction API",
    description=(
        "Predicts a student's next-day happiness score (1–5) from today's "
        "behavioral sensor data, EMA responses, and baseline survey scores."
    ),
    version="1.0.0",
)


# ── Request / Response schemas ────────────────────────────────────────────────

class PredictRequest(BaseModel):
    user_id: Annotated[str, Field(examples=["u01"], description="Student user ID, e.g. u01")]
    date: Annotated[
        Optional[date],
        Field(
            examples=["2013-04-15"],
            description=(
                "Calendar date whose features will be used (YYYY-MM-DD). "
                "Defaults to the user's most recent data day."
            ),
        ),
    ] = None


class PredictResponse(BaseModel):
    user_id: str
    features_from_date: str = Field(
        ..., description="The day whose sensor/EMA data was used as features."
    )
    prediction_for_date: str = Field(
        ..., description="The day for which the happy score is predicted."
    )
    predicted_happy_score: float = Field(
        ..., ge=1.0, le=5.0, description="Predicted happy score on the 1–5 scale."
    )


class TrainResponse(BaseModel):
    status: str
    cv_mae: float = Field(..., description="Mean absolute error via 5-fold time-series CV.")
    cv_std: float
    pearson_r: Optional[float] = Field(None, description="In-sample Pearson r between predicted and actual.")
    mae_low_1_2: Optional[float] = Field(None, description="In-sample MAE for true happy scores 1-2.")
    mae_high_3_5: Optional[float] = Field(None, description="In-sample MAE for true happy scores 3-5.")
    n_samples: int
    n_users: int
    features: list[str]
    perm_importances: Optional[dict] = Field(None, description="Permutation feature importances (MAE-based).")
    per_user_mae: Optional[dict] = Field(None, description="Leave-one-user-out CV MAE per user.")


class ModelInfoResponse(BaseModel):
    cv_mae: Optional[float] = None
    cv_std: Optional[float] = None
    n_samples: Optional[int] = None
    n_users: Optional[int] = None
    features: Optional[list[str]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Liveness probe. Also reports whether a trained model exists."""
    return {
        "status": "ok",
        "model_trained": config.MODEL_PATH.exists(),
    }


@app.post("/train", response_model=TrainResponse, tags=["Training"])
def train():
    """
    Train the mood prediction model on all available dataset users.

    This is a synchronous endpoint — it may take 10–30 seconds depending on
    dataset size. Once complete the new model is immediately active.
    """
    try:
        result = train_model()
        invalidate_cache()  # force predictor to reload the new artifact
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Training failed")
        raise HTTPException(status_code=500, detail=f"Training error: {e}")


@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
def predict_post(request: PredictRequest):
    """
    Predict tomorrow's happy score for a given user.

    Supply `date` (YYYY-MM-DD) to specify which day's data to use as features.
    If omitted, the user's most recent available day is used.
    """
    return _run_prediction(request.user_id, request.date)


@app.get("/predict/{user_id}", response_model=PredictResponse, tags=["Prediction"])
def predict_get(user_id: str, date: Optional[date] = None):
    """
    Convenience GET endpoint — same as POST /predict but via query params.

    Example: GET /predict/u01?date=2013-04-15
    """
    return _run_prediction(user_id, date)


@app.get("/model/info", response_model=ModelInfoResponse, tags=["System"])
def model_info():
    """Return metadata about the currently loaded model artifact."""
    try:
        artifact = load_artifact()
        return {
            "cv_mae": artifact.get("cv_mae"),
            "cv_std": artifact.get("cv_std"),
            "n_samples": artifact.get("n_samples"),
            "n_users": artifact.get("n_users"),
            "features": artifact.get("feature_cols"),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Internal helper ───────────────────────────────────────────────────────────

def _run_prediction(user_id: str, query_date: Optional[date]) -> dict:
    try:
        return predict_mood(user_id, query_date)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Prediction failed for user %s", user_id)
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")
