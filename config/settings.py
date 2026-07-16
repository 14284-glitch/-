"""Central settings loaded from environment variables without embedded secrets."""

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "台股智慧預測與分析系統"))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Taipei"))

    gcp_project_id: str | None = field(default_factory=lambda: os.getenv("GCP_PROJECT_ID") or None)
    bigquery_dataset: str = field(default_factory=lambda: os.getenv("BIGQUERY_DATASET", "stock_predictor"))
    bigquery_location: str = field(default_factory=lambda: os.getenv("BIGQUERY_LOCATION", "asia-east1"))
    google_application_credentials: str | None = field(default_factory=lambda: os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or None)

    finmind_api_token: str | None = field(default_factory=lambda: os.getenv("FINMIND_API_TOKEN") or None)
    fred_api_key: str | None = field(default_factory=lambda: os.getenv("FRED_API_KEY") or None)
    alpha_vantage_api_key: str | None = field(default_factory=lambda: os.getenv("ALPHA_VANTAGE_API_KEY") or None)

    feature_version: str = field(default_factory=lambda: os.getenv("FEATURE_VERSION", "v1"))
    model_artifact_dir: Path = field(default_factory=lambda: Path(os.getenv("MODEL_ARTIFACT_DIR", str(PROJECT_ROOT / "artifacts" / "models"))))

    signal_strong_buy_threshold: float = field(default_factory=lambda: _float_env("SIGNAL_STRONG_BUY_THRESHOLD", 0.70))
    signal_bullish_threshold: float = field(default_factory=lambda: _float_env("SIGNAL_BULLISH_THRESHOLD", 0.60))
    signal_bearish_threshold: float = field(default_factory=lambda: _float_env("SIGNAL_BEARISH_THRESHOLD", 0.40))
    signal_high_risk_threshold: float = field(default_factory=lambda: _float_env("SIGNAL_HIGH_RISK_THRESHOLD", 0.30))

    backtest_commission_rate: float = field(default_factory=lambda: _float_env("BACKTEST_COMMISSION_RATE", 0.001425))
    backtest_transaction_tax_rate: float = field(default_factory=lambda: _float_env("BACKTEST_TRANSACTION_TAX_RATE", 0.003))
    backtest_slippage_rate: float = field(default_factory=lambda: _float_env("BACKTEST_SLIPPAGE_RATE", 0.001))
    backtest_max_positions: int = field(default_factory=lambda: _int_env("BACKTEST_MAX_POSITIONS", 10))
    backtest_max_position_weight: float = field(default_factory=lambda: _float_env("BACKTEST_MAX_POSITION_WEIGHT", 0.20))

    def __post_init__(self) -> None:
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        thresholds = (
            self.signal_high_risk_threshold,
            self.signal_bearish_threshold,
            self.signal_bullish_threshold,
            self.signal_strong_buy_threshold,
        )
        if any(value < 0 or value > 1 for value in thresholds):
            raise ValueError("signal thresholds must be between 0 and 1")
        if thresholds != tuple(sorted(thresholds)):
            raise ValueError("signal thresholds must be ordered from high-risk to strong-buy")
        if self.backtest_max_positions <= 0 or not 0 < self.backtest_max_position_weight <= 1:
            raise ValueError("backtest position limits are invalid")

    @property
    def bigquery_table_prefix(self) -> str:
        if not self.gcp_project_id:
            raise RuntimeError("GCP_PROJECT_ID is required for BigQuery operations")
        return f"{self.gcp_project_id}.{self.bigquery_dataset}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv_if_available()
    return Settings()

