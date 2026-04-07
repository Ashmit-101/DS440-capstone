import pandas as pd
from pathlib import Path

# PHQ-9 Likert response → numeric score (0-3 per item, max total = 27)
PHQ9_RESPONSE_MAP = {
    "not at all": 0,
    "several days": 1,
    "more than half the days": 2,
    "nearly every day": 3,
}

# The last question asks about functional difficulty (not scored in standard PHQ-9)
DIFFICULTY_COLS_KEYWORDS = ["difficult", "attend"]


def load_phq9_scores(phq9_path: Path) -> pd.DataFrame:
    """
    Load pre-assessment PHQ-9 scores per user.

    Returns: user_id, phq9_score (0-27)
    """
    if not phq9_path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(phq9_path)
        df.columns = [c.strip() for c in df.columns]

        # Keep only pre-assessment rows
        if "type" in df.columns:
            df = df[df["type"].str.strip().str.lower() == "pre"].copy()

        # Identify PHQ-9 question columns (exclude uid, type, Response/difficulty)
        skip_cols = {"uid", "type", "response"}
        question_cols = [
            c for c in df.columns
            if c.lower() not in skip_cols
            and not any(kw in c.lower() for kw in DIFFICULTY_COLS_KEYWORDS)
        ]

        def compute_score(row):
            total = 0
            for col in question_cols:
                val = str(row.get(col, "")).strip().lower()
                total += PHQ9_RESPONSE_MAP.get(val, 0)
            return total

        df["phq9_score"] = df.apply(compute_score, axis=1)

        uid_col = "uid" if "uid" in df.columns else df.columns[0]
        result = df[[uid_col, "phq9_score"]].rename(columns={uid_col: "user_id"})
        return result.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()
