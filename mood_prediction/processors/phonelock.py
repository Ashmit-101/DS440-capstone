import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_phonelock_features(user_id: str, phonelock_dir: Path) -> pd.DataFrame:
    """
    Load phone lock/unlock intervals for a user.

    Rows represent locked periods (start, end timestamps).
    Total locked seconds and number of lock events per day are extracted.
    Returns: user_id, date, phone_locked_duration, phone_lock_events
    """
    path = phonelock_dir / f"phonelock_{user_id}.csv"
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
                phone_locked_duration=("duration", "sum"),
                phone_lock_events=("duration", "count"),
            )
            .reset_index()
        )
        daily["user_id"] = user_id
        return daily
    except Exception:
        return pd.DataFrame()
