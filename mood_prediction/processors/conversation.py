import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


def load_conversation_features(user_id: str, conversation_dir: Path) -> pd.DataFrame:
    """
    Load conversation detection intervals for a user.

    Returns: user_id, date, conversation_duration (seconds), conversation_count
    """
    path = conversation_dir / f"conversation_{user_id}.csv"
    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]

        # Normalize column names — file uses start_timestamp / end_timestamp
        rename = {}
        for c in df.columns:
            lc = c.lower()
            if "start" in lc:
                rename[c] = "start"
            elif "end" in lc:
                rename[c] = "end"
        df = df.rename(columns=rename)

        df["start"] = pd.to_numeric(df["start"], errors="coerce")
        df["end"] = pd.to_numeric(df["end"], errors="coerce")
        df = df.dropna(subset=["start", "end"])
        df["duration"] = df["end"] - df["start"]
        df = df[df["duration"] > 0]

        df["date"] = df["start"].apply(
            lambda t: datetime.fromtimestamp(t, tz=timezone.utc).date()
        )

        daily = (
            df.groupby("date")
            .agg(
                conversation_duration=("duration", "sum"),
                conversation_count=("duration", "count"),
            )
            .reset_index()
        )
        daily["user_id"] = user_id
        return daily
    except Exception:
        return pd.DataFrame()
