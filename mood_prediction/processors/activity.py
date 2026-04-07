import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_activity_features(user_id: str, activity_dir: Path) -> pd.DataFrame:
    """
    Load per-minute activity inference for a user.

    Activity codes: 0=stationary, 1=walking, 2=running, 3=unknown, etc.
    Returns daily aggregated: user_id, date, activity_mean, activity_std,
                              activity_count, activity_nonzero_frac
    """
    path = activity_dir / f"activity_{user_id}.csv"
    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, header=0, names=["timestamp", "activity"])
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        df["activity"] = pd.to_numeric(df["activity"], errors="coerce")
        df = df.dropna()

        df["date"] = df["timestamp"].apply(
            lambda t: datetime.fromtimestamp(t, tz=timezone.utc).date()
        )

        daily = (
            df.groupby("date")
            .agg(
                activity_mean=("activity", "mean"),
                activity_std=("activity", "std"),
                activity_count=("activity", "count"),
                activity_nonzero=("activity", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )
        # Fraction of minutes with nonzero activity
        daily["activity_nonzero_frac"] = daily["activity_nonzero"] / daily["activity_count"]
        daily["user_id"] = user_id
        return daily
    except Exception:
        return pd.DataFrame()
