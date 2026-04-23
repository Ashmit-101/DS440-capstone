"""
FastAPI application for mood prediction.

Endpoints
---------
GET  /health            — liveness check + model status
POST /train             — train (or retrain) the model synchronously
POST /train-survey      — train the survey-native model synchronously
POST /predict           — predict tomorrow's happy score for a user
POST /predict/manual    — predict from 1–5 survey inputs for the mobile POC
GET  /predict/{user_id} — predict using most recent data (convenience GET)
GET  /survey/schema     — fields required for the manual-survey prediction flow
GET  /model/info        — metadata about the currently loaded model
"""

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

# Make project root importable when the app is run from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import config
from model.trainer import train_model, train_survey_model
from model.predictor import (
    get_manual_survey_fields,
    invalidate_cache,
    load_artifact,
    predict_mood,
    predict_mood_from_survey,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_WEB_DIST = Path(__file__).parent.parent.parent / "mobile-app" / "dist"

app = FastAPI(
    title="Mood Prediction API",
    description=(
        "Predicts a student's next-day happiness score (1–5) from today's "
        "behavioral sensor data, EMA responses, and baseline survey scores."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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


class HealthDataResponse(BaseModel):
    sleep_hours: Optional[float] = Field(None, description="Hours of sleep from Apple Health")
    steps: Optional[float] = Field(None, description="Step count from Apple Health")
    calories_burned: Optional[float] = Field(None, description="Calories burned from Apple Health")


class PredictResponse(BaseModel):
    features_from_date: str = Field(
        ..., description="The day whose sensor/EMA data was used as features."
    )
    prediction_for_date: str = Field(
        ..., description="The day for which the happy score is predicted."
    )
    predicted_happy_score: float = Field(
        ..., ge=1.0, le=5.0, description="Predicted happy score on the 1–5 scale."
    )
    model_cv_mae: Optional[float] = Field(
        None, description="Cross-validated MAE for the trained model. Lower is better."
    )
    model_cv_std: Optional[float] = Field(
        None, description="Fold-to-fold variation for cross-validated MAE."
    )
    summary: Optional[str] = Field(
        None, description="Short plain-language summary of the forecast."
    )
    likely_drivers: Optional[list[str]] = Field(
        None, description="A few factors that most likely influenced the estimate."
    )
    confidence_note: Optional[str] = Field(
        None, description="A short caveat about how to interpret the estimate."
    )
    health_data: Optional[HealthDataResponse] = Field(
        None, description="Mock Apple Health data used in prediction (demo mode)."
    )
    forecast_descriptor: Optional[str] = Field(
        None, description="User-facing descriptor for the forecast band."
    )
    forecast_range_low: Optional[float] = Field(
        None, description="Lower bound of the forecast descriptor band."
    )
    forecast_range_high: Optional[float] = Field(
        None, description="Upper bound of the forecast descriptor band."
    )
    forecast_range_label: Optional[str] = Field(
        None, description="Compact display label for the forecast band."
    )


Likert = Annotated[int, Field(ge=1, le=5, description="Likert-style rating from 1 to 5.")]


class ManualPredictRequest(BaseModel):
    mood_today: Likert
    energy_today: Likert
    stress_today: Likert
    sleep_quality: Likert
    social_connection: Likert
    journal_note: Optional[str] = Field(
        default=None,
        max_length=280,
        description="Optional reflection entered by the user. Not yet used by the model.",
    )


class SurveyField(BaseModel):
    key: str
    label: str
    description: str
    scale_low: str
    scale_high: str


class SurveySchemaResponse(BaseModel):
    fields: list[SurveyField]


class TrainResponse(BaseModel):
    status: str
    cv_mae: float = Field(..., description="Mean absolute error via 5-fold time-series CV.")
    cv_std: float
    insample_mae: Optional[float] = Field(None, description="In-sample MAE (lower than CV MAE indicates overfitting).")
    overfit_gap: Optional[float] = Field(None, description="CV MAE minus in-sample MAE; >0.3 suggests overfitting.")
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


@app.post("/train-survey", response_model=TrainResponse, tags=["Training"])
def train_survey():
    """
    Train the survey-native mood model used by POST /predict/manual.
    """
    try:
        result = train_survey_model()
        invalidate_cache()
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Survey training failed")
        raise HTTPException(status_code=500, detail=f"Training error: {e}")


@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
def predict_post(request: PredictRequest):
    """
    Predict tomorrow's happy score for a given user.

    Supply `date` (YYYY-MM-DD) to specify which day's data to use as features.
    If omitted, the user's most recent available day is used.
    """
    return _run_prediction(request.user_id, request.date)


@app.post("/predict/manual", response_model=PredictResponse, tags=["Prediction"])
def predict_manual(request: ManualPredictRequest):
    """
    Predict tomorrow's happy score from user-entered 1-5 survey inputs.

    This endpoint is intended for frontend/mobile POC flows where raw sensor
    data is not yet being collected on-device.
    """
    try:
        payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
        return predict_mood_from_survey(payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Manual prediction failed")
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")


@app.get("/predict/{user_id}", response_model=PredictResponse, tags=["Prediction"])
def predict_get(user_id: str, date: Optional[date] = None):
    """
    Convenience GET endpoint — same as POST /predict but via query params.

    Example: GET /predict/u01?date=2013-04-15
    """
    return _run_prediction(user_id, date)


@app.get("/survey/schema", response_model=SurveySchemaResponse, tags=["Prediction"])
def survey_schema():
    """Return the manual-survey fields needed for the mobile POC."""
    return {"fields": get_manual_survey_fields()}


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


# ── Frontend catch-all (must come after all API routes) ───────────────────────

@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    """Serve the Expo web build; fall back to index.html for SPA routing."""
    if not _WEB_DIST.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Frontend not built. Run: "
                "cd mobile-app && npx expo export --platform web"
            ),
        )
    candidate = _WEB_DIST / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(_WEB_DIST / "index.html")


# ── Internal helper ───────────────────────────────────────────────────────────

def _run_prediction(user_id: str, query_date: Optional[date]) -> dict:
    try:
        prediction = predict_mood(user_id, query_date)
        artifact = load_artifact()
        prediction["model_cv_mae"] = artifact.get("cv_mae")
        prediction["model_cv_std"] = artifact.get("cv_std")
        return prediction
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Prediction failed for user %s", user_id)
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")
