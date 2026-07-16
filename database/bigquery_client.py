"""BigQuery dataset/table initialization and validated JSON row writes."""

from collections.abc import Iterable, Mapping
from typing import Any

from config.settings import Settings, get_settings
from database.schemas import TABLE_SPECS, to_bigquery_schema


class BigQueryRepository:
    def __init__(self, settings: Settings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gcp_project_id:
            raise RuntimeError("GCP_PROJECT_ID is required for BigQuery operations")
        if client is None:
            from google.cloud import bigquery

            client = bigquery.Client(project=self.settings.gcp_project_id, location=self.settings.bigquery_location)
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
            if spec.partition_field:
                table.time_partitioning = bigquery.TimePartitioning(
                    type_=bigquery.TimePartitioningType.DAY,
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
