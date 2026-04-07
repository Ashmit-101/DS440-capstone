import json
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_sleep_features(user_id: str, sleep_dir: Path) -> pd.DataFrame:
    """
    Load Sleep EMA for a user.

    Relevant fields: hour (hours slept), rate (quality 1-5), resp_time
    Returns daily aggregated: user_id, date, sleep_hours, sleep_rate
    """
    path = sleep_dir / f"Sleep_{user_id}.json"
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

        # "hour" = hours slept, "rate" = sleep quality 1-5
        hour = None
        rate = None
        if "hour" in entry:
            try:
                h = float(entry["hour"])
                if 0 < h <= 24:
                    hour = h
            except (ValueError, TypeError):
                pass
        if "rate" in entry:
            try:
                r = float(entry["rate"])
                if 1 <= r <= 5:
                    rate = r
            except (ValueError, TypeError):
                pass

        if hour is None and rate is None:
            continue

        records.append({"date": date, "sleep_hours": hour, "sleep_rate": rate})

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    daily = (
        df.groupby("date")
        .agg(sleep_hours=("sleep_hours", "mean"), sleep_rate=("sleep_rate", "mean"))
        .reset_index()
    )
    daily["user_id"] = user_id
    return daily
