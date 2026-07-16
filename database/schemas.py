"""Canonical BigQuery table schemas, partitioning, clustering, and logical keys."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: str
    mode: str = "NULLABLE"
    description: str = ""


@dataclass(frozen=True)
class TableSpec:
    fields: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...]
    partition_field: str | None = None
    clustering_fields: tuple[str, ...] = ()
    require_partition_filter: bool = False


def f(name: str, field_type: str, mode: str = "NULLABLE", description: str = "") -> FieldSpec:
    return FieldSpec(name, field_type, mode, description)


TABLE_SPECS: dict[str, TableSpec] = {
    "stock_master": TableSpec((
        f("stock_id", "STRING", "REQUIRED"), f("stock_name", "STRING", "REQUIRED"),
        f("market", "STRING", "REQUIRED"), f("industry", "STRING"), f("listing_date", "DATE"),
        f("delisting_date", "DATE"), f("currency", "STRING", "REQUIRED"), f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("stock_id",), clustering_fields=("market", "industry")),
    "tw_stock_daily": TableSpec((
        f("stock_id", "STRING", "REQUIRED"), f("trade_date", "DATE", "REQUIRED"),
        f("open", "FLOAT64"), f("high", "FLOAT64"), f("low", "FLOAT64"), f("close", "FLOAT64"),
        f("adjusted_close", "FLOAT64"), f("volume", "INT64"), f("turnover", "FLOAT64"),
        f("transaction_count", "INT64"), f("return_1d", "FLOAT64"), f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("stock_id", "trade_date"), "trade_date", ("stock_id",), True),
    "us_market_daily": TableSpec((
        f("us_trade_date", "DATE", "REQUIRED"),
        f("data_available_datetime", "TIMESTAMP", "REQUIRED", "Actual time the data became observable"),
        f("tw_effective_trade_date", "DATE", "REQUIRED", "First Taiwan session that may use this row"),
        f("sp500_return", "FLOAT64"), f("nasdaq100_return", "FLOAT64"), f("dow_return", "FLOAT64"),
        f("sox_return", "FLOAT64"), f("russell2000_return", "FLOAT64"), f("vix_close", "FLOAT64"),
        f("vix_change", "FLOAT64"), f("us2y_yield", "FLOAT64"), f("us10y_yield", "FLOAT64"),
        f("us10y_change", "FLOAT64"), f("dxy_return", "FLOAT64"), f("wti_return", "FLOAT64"),
        f("gold_return", "FLOAT64"), f("nasdaq_futures_change", "FLOAT64"), f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("us_trade_date",), "tw_effective_trade_date", (), True),
    "us_stock_daily": TableSpec((
        f("ticker", "STRING", "REQUIRED"), f("us_trade_date", "DATE", "REQUIRED"),
        f("data_available_datetime", "TIMESTAMP", "REQUIRED"), f("tw_effective_trade_date", "DATE", "REQUIRED"),
        f("open", "FLOAT64"), f("high", "FLOAT64"), f("low", "FLOAT64"), f("close", "FLOAT64"),
        f("adjusted_close", "FLOAT64"), f("volume", "INT64"), f("return_1d", "FLOAT64"),
        f("return_5d", "FLOAT64"), f("volume_ratio_20d", "FLOAT64"), f("gap_return", "FLOAT64"),
        f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("ticker", "us_trade_date"), "tw_effective_trade_date", ("ticker",), True),
    "institutional_trading": TableSpec((
        f("stock_id", "STRING", "REQUIRED"), f("trade_date", "DATE", "REQUIRED"),
        f("foreign_buy", "INT64"), f("foreign_sell", "INT64"), f("foreign_net", "INT64"),
        f("investment_trust_net", "INT64"), f("dealer_net", "INT64"), f("institutional_net", "INT64"),
        f("margin_balance", "INT64"), f("margin_change", "INT64"), f("short_balance", "INT64"),
        f("short_change", "INT64"), f("securities_lending", "INT64"), f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("stock_id", "trade_date"), "trade_date", ("stock_id",), True),
    "financial_statement": TableSpec((
        f("stock_id", "STRING", "REQUIRED"), f("report_period", "DATE", "REQUIRED"),
        f("announcement_datetime", "TIMESTAMP", "REQUIRED", "Actual public announcement time"),
        f("effective_trade_date", "DATE", "REQUIRED", "First Taiwan session after announcement when usable"),
        f("revenue", "FLOAT64"), f("revenue_yoy", "FLOAT64"), f("revenue_mom", "FLOAT64"),
        f("gross_profit", "FLOAT64"), f("gross_margin", "FLOAT64"), f("operating_income", "FLOAT64"),
        f("operating_margin", "FLOAT64"), f("net_income", "FLOAT64"), f("eps", "FLOAT64"), f("roe", "FLOAT64"),
        f("debt_ratio", "FLOAT64"), f("free_cash_flow", "FLOAT64"), f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("stock_id", "report_period", "announcement_datetime"), "effective_trade_date", ("stock_id",), True),
    "technical_features": TableSpec((
        f("stock_id", "STRING", "REQUIRED"), f("trade_date", "DATE", "REQUIRED"),
        *(f(name, "FLOAT64") for name in (
            "ma5", "ma10", "ma20", "ma60", "ma120", "ma240", "ema12", "ema26", "rsi14", "macd",
            "macd_signal", "macd_histogram", "kd_k", "kd_d", "adx", "plus_di", "minus_di", "atr14",
            "bollinger_upper", "bollinger_middle", "bollinger_lower", "bollinger_width", "obv", "volume_ma20",
            "volume_ratio_20d", "bias5", "bias20", "volatility20", "relative_strength_market",
        )), f("updated_at", "TIMESTAMP", "REQUIRED"),
    ), ("stock_id", "trade_date"), "trade_date", ("stock_id",), True),
    "prediction_target": TableSpec((
        f("stock_id", "STRING", "REQUIRED"), f("trade_date", "DATE", "REQUIRED"),
        f("return_1d", "FLOAT64"), f("return_5d", "FLOAT64"), f("return_20d", "FLOAT64"),
        f("up_1d", "BOOL"), f("up_5d", "BOOL"), f("up_20d", "BOOL"),
        f("max_return_20d", "FLOAT64"), f("max_drawdown_20d", "FLOAT64"),
    ), ("stock_id", "trade_date"), "trade_date", ("stock_id",), True),
    "model_prediction": TableSpec((
        f("model_id", "STRING", "REQUIRED"), f("model_version", "STRING", "REQUIRED"),
        f("stock_id", "STRING", "REQUIRED"), f("prediction_datetime", "TIMESTAMP", "REQUIRED"),
        f("prediction_for_date", "DATE", "REQUIRED"), f("probability_up_1d", "FLOAT64"),
        f("probability_up_5d", "FLOAT64"), f("probability_up_20d", "FLOAT64"),
        f("predicted_return_1d", "FLOAT64"), f("predicted_return_5d", "FLOAT64"),
        f("predicted_return_20d", "FLOAT64"), f("signal", "STRING"), f("confidence_level", "STRING"),
        f("risk_level", "STRING"), f("feature_version", "STRING", "REQUIRED"), f("created_at", "TIMESTAMP", "REQUIRED"),
    ), ("model_id", "model_version", "stock_id", "prediction_datetime", "prediction_for_date"),
       "prediction_for_date", ("stock_id", "model_id"), True),
    "model_registry": TableSpec((
        f("model_id", "STRING", "REQUIRED"), f("model_name", "STRING", "REQUIRED"),
        f("model_version", "STRING", "REQUIRED"), f("target_name", "STRING", "REQUIRED"),
        f("training_start", "DATE", "REQUIRED"), f("training_end", "DATE", "REQUIRED"),
        f("validation_period", "STRING"), f("test_period", "STRING"), f("feature_version", "STRING", "REQUIRED"),
        f("model_parameters", "JSON"), f("accuracy", "FLOAT64"), f("precision", "FLOAT64"),
        f("recall", "FLOAT64"), f("f1_score", "FLOAT64"), f("roc_auc", "FLOAT64"),
        f("sharpe_ratio", "FLOAT64"), f("max_drawdown", "FLOAT64"), f("created_at", "TIMESTAMP", "REQUIRED"),
    ), ("model_id", "model_version", "target_name"), clustering_fields=("model_id", "target_name")),
}


def to_bigquery_schema(table_name: str) -> list[object]:
    """Convert dependency-free specs into google.cloud.bigquery.SchemaField objects."""
    from google.cloud import bigquery

    return [bigquery.SchemaField(item.name, item.field_type, mode=item.mode, description=item.description)
            for item in TABLE_SPECS[table_name].fields]

