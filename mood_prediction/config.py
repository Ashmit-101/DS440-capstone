from pathlib import Path

# Root of the dataset (relative to project root, one level up from mood_prediction/)
DATASET_ROOT = Path(__file__).parent.parent / "dataset"

# EMA response directories
MOOD_DIR = DATASET_ROOT / "EMA/response/Mood"
SLEEP_DIR = DATASET_ROOT / "EMA/response/Sleep"
STRESS_DIR = DATASET_ROOT / "EMA/response/Stress"
EXERCISE_DIR = DATASET_ROOT / "EMA/response/Exercise"

# Sensing directories
ACTIVITY_DIR = DATASET_ROOT / "sensing/activity"
PHONELOCK_DIR = DATASET_ROOT / "sensing/phonelock"
DARK_DIR = DATASET_ROOT / "sensing/dark"
CONVERSATION_DIR = DATASET_ROOT / "sensing/conversation"

# Survey
PHQ9_PATH = DATASET_ROOT / "survey/PHQ-9.csv"

# Trained model artifact
MODEL_PATH = Path(__file__).parent / "model_artifacts" / "mood_model.pkl"
SURVEY_MODEL_PATH = Path(__file__).parent / "model_artifacts" / "mood_model_survey.pkl"
