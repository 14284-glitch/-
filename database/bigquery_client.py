"""BigQuery dataset/table initialization and validated JSON row writes."""

from collections.abc import Iterable, Mapping
import json
import os
from typing import Any
from uuid import uuid4

from config.settings import Settings, get_settings
from database.schemas import TABLE_SPECS, to_bigquery_schema


class BigQueryRepository:
    def __init__(self, settings: Settings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gcp_project_id:
            raise RuntimeError("GCP_PROJECT_ID is required for BigQuery operations")
        if client is None:
            from google.cloud import bigquery
            credentials = None
            credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            if credentials_json:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_info(json.loads(credentials_json))
            client = bigquery.Client(
                project=self.settings.gcp_project_id,
                location=self.settings.bigquery_location,
                credentials=credentials,
            )
        self.client = client

    @property
    def dataset_id(self) -> str:
        return f"{self.settings.gcp_project_id}.{self.settings.bigquery_dataset}"

    def initialize(self) -> list[str]:
        """Create the dataset and missing tables; existing data is never deleted."""
        from google.cloud import bigquery

        dataset = bigquery.Dataset(self.dataset_id)
        dataset.location = self.settings.bigquery_location
        dataset.description = "Taiwan stock predictor point-in-time research data"
        self.client.create_dataset(dataset, exists_ok=True)
        created: list[str] = []
        for name, spec in TABLE_SPECS.items():
            table = bigquery.Table(f"{self.dataset_id}.{name}", schema=to_bigquery_schema(name))
            sandbox_mode = os.getenv("BIGQUERY_SANDBOX_MODE", "false").lower() in {
                "1", "true", "yes", "on"
            }
            if spec.partition_field and not sandbox_mode:
                table.time_partitioning = bigquery.TimePartitioning(
                    # Monthly partitions keep 8–10 years of market history
                    # well below BigQuery's 4,000-partition load-job limit.
                    type_=bigquery.TimePartitioningType.MONTH,
                    field=spec.partition_field,
                )
                table.require_partition_filter = spec.require_partition_filter
            table.clustering_fields = list(spec.clustering_fields) or None
            table.description = f"Logical primary key: {', '.join(spec.primary_key)}"
            self.client.create_table(table, exists_ok=True)
            created.append(name)
        return created

    def insert_rows(self, table_name: str, rows: Iterable[Mapping[str, Any]]) -> int:
        """Insert rows after required-field, unknown-field, and duplicate-key checks."""
        if table_name not in TABLE_SPECS:
            raise KeyError(f"Unknown table: {table_name}")
        materialized = [dict(row) for row in rows]
        if not materialized:
            return 0
        spec = TABLE_SPECS[table_name]
        allowed = {field.name for field in spec.fields}
        required = {field.name for field in spec.fields if field.mode == "REQUIRED"}
        keys: set[tuple[Any, ...]] = set()
        for index, row in enumerate(materialized):
            missing = required - row.keys()
            unknown = row.keys() - allowed
            if missing:
                raise ValueError(f"row {index} missing required fields: {sorted(missing)}")
            if unknown:
                raise ValueError(f"row {index} contains unknown fields: {sorted(unknown)}")
            key = tuple(row.get(name) for name in spec.primary_key)
            if None in key:
                raise ValueError(f"row {index} has null logical primary key")
            if key in keys:
                raise ValueError(f"duplicate logical primary key in batch: {key}")
            keys.add(key)
        errors = self.client.insert_rows_json(f"{self.dataset_id}.{table_name}", materialized)
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")
        return len(materialized)

    def merge_rows(self, table_name: str, rows: Iterable[Mapping[str, Any]]) -> int:
        """Idempotently upsert rows through a short-lived staging table."""
        materialized = [dict(row) for row in rows]
        if not materialized:
            return 0
        self._validate_rows(table_name, materialized)
        from google.cloud import bigquery

        spec = TABLE_SPECS[table_name]
        target = f"{self.dataset_id}.{table_name}"
        staging = f"{self.dataset_id}._stage_{table_name}_{uuid4().hex[:10]}"
        job_config = bigquery.LoadJobConfig(
            schema=to_bigquery_schema(table_name),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        try:
            self.client.load_table_from_json(materialized, staging, job_config=job_config).result()
            fields = [field.name for field in spec.fields]
            predicate = " AND ".join(f"T.{key}=S.{key}" for key in spec.primary_key)
            if spec.partition_field and spec.partition_field not in spec.primary_key:
                predicate += f" AND T.{spec.partition_field}=S.{spec.partition_field}"
            updates = ", ".join(f"{field}=S.{field}" for field in fields if field not in spec.primary_key)
            columns = ", ".join(fields)
            values = ", ".join(f"S.{field}" for field in fields)
            sql = (
                f"MERGE `{target}` T USING `{staging}` S ON {predicate} "
                f"WHEN MATCHED THEN UPDATE SET {updates} "
                f"WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values})"
            )
            self.client.query(sql).result()
        finally:
            self.client.delete_table(staging, not_found_ok=True)
        return len(materialized)

    def replace_dataframe(self, table_name: str, frame: Any) -> int:
        """Atomically replace a table with a validated DataFrame.

        BigQuery Sandbox does not permit DML statements such as MERGE. A load
        job with WRITE_TRUNCATE remains available, avoids duplicate rows, and
        makes scheduled full-table synchronization usable without billing.
        """
        if table_name not in TABLE_SPECS:
            raise KeyError(f"Unknown table: {table_name}")
        if frame.empty:
            return 0

        spec = TABLE_SPECS[table_name]
        allowed = {field.name for field in spec.fields}
        required = {field.name for field in spec.fields if field.mode == "REQUIRED"}
        frame = frame.copy()
        columns = set(frame.columns)
        missing = required - columns
        unknown = columns - allowed
        if missing:
            raise ValueError(f"DataFrame missing required fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"DataFrame contains unknown fields: {sorted(unknown)}")
        if frame[list(spec.primary_key)].isnull().any().any():
            raise ValueError("DataFrame contains null logical primary keys")
        if frame.duplicated(subset=list(spec.primary_key)).any():
            raise ValueError("DataFrame contains duplicate logical primary keys")
        for field in spec.fields:
            if field.name not in frame.columns:
                frame[field.name] = None
        frame = frame[[field.name for field in spec.fields]]
        import pandas as pd

        for field in spec.fields:
            if field.field_type == "DATE":
                frame[field.name] = pd.to_datetime(frame[field.name], errors="coerce").dt.date
            elif field.field_type == "TIMESTAMP":
                frame[field.name] = pd.to_datetime(frame[field.name], errors="coerce", utc=True)
            elif field.field_type in {"FLOAT64", "NUMERIC"}:
                frame[field.name] = pd.to_numeric(frame[field.name], errors="coerce")
            elif field.field_type == "INT64":
                frame[field.name] = pd.to_numeric(frame[field.name], errors="coerce").astype("Int64")
            elif field.field_type == "BOOL":
                frame[field.name] = frame[field.name].astype("boolean")

        from google.cloud import bigquery

        target = f"{self.dataset_id}.{table_name}"
        frames = [frame]

        for index, load_frame in enumerate(frames):
            job_config = bigquery.LoadJobConfig(
                schema=to_bigquery_schema(table_name),
                write_disposition=(
                    bigquery.WriteDisposition.WRITE_TRUNCATE
                    if index == 0
                    else bigquery.WriteDisposition.WRITE_APPEND
                ),
            )
            self.client.load_table_from_dataframe(
                load_frame, target, job_config=job_config
            ).result()
        return len(frame)

    def _validate_rows(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        if table_name not in TABLE_SPECS:
            raise KeyError(f"Unknown table: {table_name}")
        spec = TABLE_SPECS[table_name]
        allowed = {field.name for field in spec.fields}
        required = {field.name for field in spec.fields if field.mode == "REQUIRED"}
        seen = set()
        for index, row in enumerate(rows):
            if required - row.keys():
                raise ValueError(f"row {index} missing required fields: {sorted(required - row.keys())}")
            if row.keys() - allowed:
                raise ValueError(f"row {index} contains unknown fields: {sorted(row.keys() - allowed)}")
            key = tuple(row.get(name) for name in spec.primary_key)
            if None in key or key in seen:
                raise ValueError(f"invalid or duplicate logical primary key: {key}")
            seen.add(key)
