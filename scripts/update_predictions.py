"""Create validated forecasts, preserve snapshots, and reconcile matured outcomes."""

from __future__ import annotations

from pathlib import Path

from config.settings import PROJECT_ROOT
from models.prediction_ledger import record_forecasts, reconcile_outcomes, write_latest
from models.validated_logistic import train_validated_forecasts


def update_validated_predictions(raw_root: Path | None = None) -> dict[str, object]:
    raw_root = raw_root or PROJECT_ROOT / "data" / "raw" / "tw"
    forecasts, completed, failed = [], [], {}
    for path in sorted(raw_root.glob("*_TW.csv")):
        try:
            results = train_validated_forecasts(path)
            forecasts.extend(results)
            completed.append(path.stem.replace("_TW", ".TW"))
        except (ValueError, OSError) as exc:
            failed[path.stem] = str(exc)
    reconcile_outcomes(raw_root=raw_root)
    if forecasts:
        record_forecasts(forecasts)
        write_latest(forecasts)
    return {"completed": completed, "failed": failed, "forecast_rows": len(forecasts)}


if __name__ == "__main__":
    print(update_validated_predictions())
