import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_dark_features(user_id: str, dark_dir: Path) -> pd.DataFrame:
    """
    Load screen-off (dark) intervals for a user.

    Returns: user_id, date, screen_off_duration (seconds), screen_off_events
    """
    path = dark_dir / f"dark_{user_id}.csv"
    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        df["start"] = pd.to_numeric(df["start"], errors="coerce")
        df["end"] = pd.to_numeric(df["end"], errors="coerce")
        df = df.dropna()
        df["duration"] = df["end"] - df["start"]
        df = df[df["duration"] > 0]

        df["date"] = df["start"].apply(
            lambda t: datetime.fromtimestamp(t, tz=timezone.utc).date()
        )

        daily = (
            df.groupby("date")
            .agg(
                screen_off_duration=("duration", "sum"),
                screen_off_events=("duration", "count"),
            )
            .reset_index()
        )
        daily["user_id"] = user_id
        return daily
    except Exception:
        return pd.DataFrame()
