"""Create the BigQuery dataset and all canonical tables without deleting data."""

import argparse

from config.settings import get_settings
from database.bigquery_client import BigQueryRepository
from database.schemas import TABLE_SPECS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true", help="Validate local schemas without cloud access")
    args = parser.parse_args()
    if args.validate_only:
        for name, spec in TABLE_SPECS.items():
            print(f"OK {name}: {len(spec.fields)} fields; key={','.join(spec.primary_key)}")
        return 0
    settings = get_settings()
    repository = BigQueryRepository(settings)
    tables = repository.initialize()
    print(f"Initialized {len(tables)} tables in {repository.dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

