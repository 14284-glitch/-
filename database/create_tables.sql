-- BigQuery Standard SQL. Replace PROJECT_ID and DATASET_ID before execution.
-- Primary keys are logical and NOT ENFORCED; ingestion code validates batch uniqueness.

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.stock_master` (
  stock_id STRING NOT NULL, stock_name STRING NOT NULL, market STRING NOT NULL,
  industry STRING, listing_date DATE, delisting_date DATE, currency STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (stock_id) NOT ENFORCED
) CLUSTER BY market, industry;

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.tw_stock_daily` (
  stock_id STRING NOT NULL, trade_date DATE NOT NULL,
  open FLOAT64, high FLOAT64, low FLOAT64, close FLOAT64, adjusted_close FLOAT64,
  volume INT64, turnover FLOAT64, transaction_count INT64, return_1d FLOAT64,
  updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (stock_id, trade_date) NOT ENFORCED
) PARTITION BY trade_date CLUSTER BY stock_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.us_market_daily` (
  us_trade_date DATE NOT NULL,
  data_available_datetime TIMESTAMP NOT NULL OPTIONS(description='Actual time the data became observable'),
  tw_effective_trade_date DATE NOT NULL OPTIONS(description='First Taiwan session that may use this row'),
  sp500_return FLOAT64, nasdaq100_return FLOAT64, dow_return FLOAT64,
  sox_return FLOAT64, russell2000_return FLOAT64, vix_close FLOAT64, vix_change FLOAT64,
  us2y_yield FLOAT64, us10y_yield FLOAT64, us10y_change FLOAT64, dxy_return FLOAT64,
  wti_return FLOAT64, gold_return FLOAT64, nasdaq_futures_change FLOAT64,
  updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (us_trade_date) NOT ENFORCED
) PARTITION BY tw_effective_trade_date
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.us_stock_daily` (
  ticker STRING NOT NULL, us_trade_date DATE NOT NULL,
  data_available_datetime TIMESTAMP NOT NULL,
  tw_effective_trade_date DATE NOT NULL,
  open FLOAT64, high FLOAT64, low FLOAT64, close FLOAT64, adjusted_close FLOAT64,
  volume INT64, return_1d FLOAT64, return_5d FLOAT64, volume_ratio_20d FLOAT64,
  gap_return FLOAT64, updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (ticker, us_trade_date) NOT ENFORCED
) PARTITION BY tw_effective_trade_date CLUSTER BY ticker
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.institutional_trading` (
  stock_id STRING NOT NULL, trade_date DATE NOT NULL,
  foreign_buy INT64, foreign_sell INT64, foreign_net INT64,
  investment_trust_net INT64, dealer_net INT64, institutional_net INT64,
  margin_balance INT64, margin_change INT64, short_balance INT64, short_change INT64,
  securities_lending INT64, updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (stock_id, trade_date) NOT ENFORCED
) PARTITION BY trade_date CLUSTER BY stock_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.macro_observation` (
  series_id STRING NOT NULL, series_name STRING, observation_date DATE NOT NULL,
  vintage_start_date DATE NOT NULL, vintage_end_date DATE,
  data_available_date DATE NOT NULL, value FLOAT64, updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (series_id, observation_date, vintage_start_date) NOT ENFORCED
) PARTITION BY data_available_date CLUSTER BY series_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.financial_event` (
  event_id STRING NOT NULL, title STRING NOT NULL, link STRING NOT NULL, summary STRING,
  source STRING, category STRING, published_at TIMESTAMP, data_available_datetime TIMESTAMP,
  tw_effective_trade_date DATE NOT NULL, first_seen_at TIMESTAMP NOT NULL, last_seen_at TIMESTAMP NOT NULL,
  PRIMARY KEY (event_id) NOT ENFORCED
) PARTITION BY tw_effective_trade_date CLUSTER BY source
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.financial_statement` (
  stock_id STRING NOT NULL, report_period DATE NOT NULL,
  announcement_datetime TIMESTAMP NOT NULL OPTIONS(description='Actual public announcement time'),
  effective_trade_date DATE NOT NULL OPTIONS(description='First Taiwan session after announcement when usable'),
  revenue FLOAT64, revenue_yoy FLOAT64, revenue_mom FLOAT64,
  gross_profit FLOAT64, gross_margin FLOAT64, operating_income FLOAT64,
  operating_margin FLOAT64, net_income FLOAT64, eps FLOAT64, roe FLOAT64,
  debt_ratio FLOAT64, free_cash_flow FLOAT64,
  pe_ratio FLOAT64, pb_ratio FLOAT64, dividend_yield FLOAT64,
  updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (stock_id, report_period, announcement_datetime) NOT ENFORCED
) PARTITION BY effective_trade_date CLUSTER BY stock_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.technical_features` (
  stock_id STRING NOT NULL, trade_date DATE NOT NULL,
  ma5 FLOAT64, ma10 FLOAT64, ma20 FLOAT64, ma60 FLOAT64, ma120 FLOAT64, ma240 FLOAT64,
  ema12 FLOAT64, ema26 FLOAT64, rsi14 FLOAT64, macd FLOAT64, macd_signal FLOAT64,
  macd_histogram FLOAT64, kd_k FLOAT64, kd_d FLOAT64, adx FLOAT64, plus_di FLOAT64,
  minus_di FLOAT64, atr14 FLOAT64, bollinger_upper FLOAT64, bollinger_middle FLOAT64,
  bollinger_lower FLOAT64, bollinger_width FLOAT64, obv FLOAT64, volume_ma20 FLOAT64,
  volume_ratio_20d FLOAT64, bias5 FLOAT64, bias20 FLOAT64, volatility20 FLOAT64,
  relative_strength_market FLOAT64, updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (stock_id, trade_date) NOT ENFORCED
) PARTITION BY trade_date CLUSTER BY stock_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.prediction_target` (
  stock_id STRING NOT NULL, trade_date DATE NOT NULL,
  return_1d FLOAT64, return_5d FLOAT64, return_20d FLOAT64,
  up_1d BOOL, up_5d BOOL, up_20d BOOL, max_return_20d FLOAT64, max_drawdown_20d FLOAT64,
  PRIMARY KEY (stock_id, trade_date) NOT ENFORCED
) PARTITION BY trade_date CLUSTER BY stock_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.model_prediction` (
  model_id STRING NOT NULL, model_version STRING NOT NULL, stock_id STRING NOT NULL,
  prediction_datetime TIMESTAMP NOT NULL, prediction_for_date DATE NOT NULL,
  probability_up_1d FLOAT64, probability_up_5d FLOAT64, probability_up_20d FLOAT64,
  predicted_return_1d FLOAT64, predicted_return_5d FLOAT64, predicted_return_20d FLOAT64,
  signal STRING, confidence_level STRING, risk_level STRING,
  feature_version STRING NOT NULL, created_at TIMESTAMP NOT NULL,
  PRIMARY KEY (model_id, model_version, stock_id, prediction_datetime, prediction_for_date) NOT ENFORCED
) PARTITION BY prediction_for_date CLUSTER BY stock_id, model_id
OPTIONS (require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET_ID.model_registry` (
  model_id STRING NOT NULL, model_name STRING NOT NULL, model_version STRING NOT NULL,
  target_name STRING NOT NULL, training_start DATE NOT NULL, training_end DATE NOT NULL,
  validation_period STRING, test_period STRING, feature_version STRING NOT NULL,
  model_parameters JSON, accuracy FLOAT64, precision FLOAT64, recall FLOAT64,
  f1_score FLOAT64, roc_auc FLOAT64, sharpe_ratio FLOAT64, max_drawdown FLOAT64,
  created_at TIMESTAMP NOT NULL,
  PRIMARY KEY (model_id, model_version, target_name) NOT ENFORCED
) CLUSTER BY model_id, target_name;
