import json
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_stress_features(user_id: str, stress_dir: Path) -> pd.DataFrame:
    """
    Load Stress EMA for a user.

    Relevant field: level (stress level 1-5)
    Returns daily aggregated: user_id, date, stress_level
    """
    path = stress_dir / f"Stress_{user_id}.json"
    if not path.exists():
        return pd.DataFrame()

    with open(path) as f:
        data = json.load(f)

    records = []
    for entry in data:
        if "level" not in entry:
            continue
        try:
            level = float(entry["level"])
            resp_time = int(entry["resp_time"])
        except (KeyError, ValueError, TypeError):
            continue

        if not (1 <= level <= 5):
            continue

        date = datetime.fromtimestamp(resp_time, tz=timezone.utc).date()
        records.append({"date": date, "stress_level": level})

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    daily = (
        df.groupby("date")
        .agg(stress_level=("stress_level", "mean"))
        .reset_index()
    )
    daily["user_id"] = user_id
    return daily
