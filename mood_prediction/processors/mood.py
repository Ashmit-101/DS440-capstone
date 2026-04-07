import json
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_mood_ema(user_id: str, mood_dir: Path) -> pd.DataFrame:
    """
    Load Mood EMA for a user and return a daily-aggregated DataFrame.

    Columns returned: user_id, date, happy, sad, happyornot, sadornot
    """
    path = mood_dir / f"Mood_{user_id}.json"
    if not path.exists():
        return pd.DataFrame()

    with open(path) as f:
        data = json.load(f)

    records = []
    for entry in data:
        # Must have happy, sad, and resp_time
        if "happy" not in entry or "sad" not in entry:
            continue
        try:
            happy = int(entry["happy"])
            sad = int(entry["sad"])
            resp_time = int(entry["resp_time"])
        except (ValueError, TypeError):
            continue

        # Optional binary flags — may be "null" string or missing
        def _safe_int(val, default=0):
            try:
                v = int(val)
                return v if v in (0, 1, 2) else default
            except (ValueError, TypeError):
                return default

        happyornot = _safe_int(entry.get("happyornot", 0))
        sadornot = _safe_int(entry.get("sadornot", 0))

        date = datetime.fromtimestamp(resp_time, tz=timezone.utc).date()
        records.append({
            "user_id": user_id,
            "date": date,
            "happy": happy,
            "sad": sad,
            "happyornot": happyornot,
            "sadornot": sadornot,
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    # Multiple mood entries per day → take the mean
    daily = (
        df.groupby(["user_id", "date"])
        .agg(
            happy=("happy", "mean"),
            sad=("sad", "mean"),
            happyornot=("happyornot", "mean"),
            sadornot=("sadornot", "mean"),
        )
        .reset_index()
    )
    return daily
