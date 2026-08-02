"""Generic DuckDB exporter providing database abstraction and table management utilities."""

import os
from typing import Any

from civican.scraper.exporters.base import BaseExporter
from civican.scraper.utils import log_message

try:
    import duckdb

    HAS_DUCKDB = True
except ImportError:
    duckdb = None  # type: ignore[assignment]
    HAS_DUCKDB = False


class DuckDBExporter(BaseExporter):
    """Generic DuckDB exporter providing database connection, schema execution, and bulk insert utilities."""

    def __init__(self, db_path: str):
        if not HAS_DUCKDB:
            raise ImportError(
                "DuckDBExporter requires the 'duckdb' package. "
                "Install it using: pip install civican-scraper[duckdb] or uv sync --extra duckdb"
            )
        self.db_path = db_path
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = duckdb.connect(db_path)
        self._closed = False

    def execute_schema(self, sql_script: str) -> None:
        """Execute DDL schema script to initialize tables, indexes, or views."""
        self.conn.execute(sql_script)
        self.conn.commit()

    def insert_records(
        self,
        table_name: str,
        columns: list[str],
        records: list[tuple[Any, ...]],
        on_conflict: str | None = None,
    ) -> int:
        """Insert tuples into a specific table with optional conflict resolution ('replace', 'ignore')."""
        if not records or not columns:
            return 0

        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        if on_conflict == "replace":
            sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders});"
        elif on_conflict == "ignore":
            sql = f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders});"
        else:
            sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders});"

        self.conn.executemany(sql, records)
        self.conn.commit()
        log_message(f"DuckDB: inserted {len(records)} rows into '{table_name}'.")
        return len(records)

    def insert_dicts(
        self,
        table_name: str,
        dicts: list[dict[str, Any]],
        columns: list[str] | None = None,
        on_conflict: str | None = None,
    ) -> int:
        """Insert list of dictionaries into a target table."""
        if not dicts:
            return 0

        if columns is None:
            columns = list(dicts[0].keys())

        records = [tuple(d.get(col) for col in columns) for d in dicts]
        return self.insert_records(table_name, columns, records, on_conflict=on_conflict)

    def export_registrations(self, registrations: list[Any]) -> int:
        """Generic fallback implementation for BaseExporter contract."""
        _ = registrations
        return 0

    def export_communications(self, communications: list[Any]) -> int:
        """Generic fallback implementation for BaseExporter contract."""
        _ = communications
        return 0

    def close(self) -> None:
        """Commit and close connection to DuckDB."""
        if hasattr(self, "conn") and not self._closed:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass
            self._closed = True
