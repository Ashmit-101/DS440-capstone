import json
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_exercise_features(user_id: str, exercise_dir: Path) -> pd.DataFrame:
    """
    Load Exercise EMA for a user.

    Fields: exercise (intensity 1-5), have (1=yes 2=no), walk (amount), resp_time
    Returns daily aggregated: user_id, date, exercise_intensity, exercise_done, walk_amount
    """
    path = exercise_dir / f"Exercise_{user_id}.json"
    if not path.exists():
        return pd.DataFrame()

    with open(path) as f:
        data = json.load(f)

    records = []
    for entry in data:
        try:
            resp_time = int(entry["resp_time"])
        except (KeyError, ValueError, TypeError):
            continue

        date = datetime.fromtimestamp(resp_time, tz=timezone.utc).date()

        def _safe_float(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        exercise = _safe_float(entry.get("exercise"))
        have = _safe_float(entry.get("have"))
        walk = _safe_float(entry.get("walk"))

        if exercise is None and have is None and walk is None:
            continue

        records.append({
            "date": date,
            "exercise_intensity": exercise,
            "exercise_done": have,
            "walk_amount": walk,
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    daily = (
        df.groupby("date")
        .agg(
            exercise_intensity=("exercise_intensity", "mean"),
            exercise_done=("exercise_done", "mean"),
            walk_amount=("walk_amount", "mean"),
        )
        .reset_index()
    )
    daily["user_id"] = user_id
    return daily
