"""Lobby Canada specific DuckDB database exporter."""

import os
from typing import Any, ClassVar

from civican.scraper.exporters.base import BaseExporter
from civican.scraper.exporters.duckdb import DuckDBExporter


def clean_date(val: Any) -> str | None:
    """Clean date field to ensure valid ISO YYYY-MM-DD string or None for SQL NULL."""
    if not val or str(val).strip().lower() in ("", "null", "none", "n/a"):
        return None
    s = str(val).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


class LobbyCanadaDuckDBExporter(BaseExporter):
    """Lobby Canada specific database exporter wrapping the generic DuckDBExporter."""

    SCHEMA_SQL = """
        CREATE TABLE IF NOT EXISTS registrations (
            registration_id VARCHAR PRIMARY KEY,
            registrant_name VARCHAR,
            client_org_name VARCHAR,
            type VARCHAR,
            status VARCHAR,
            effective_date DATE,
            posted_date DATE
        );
        CREATE TABLE IF NOT EXISTS communications (
            communication_id VARCHAR PRIMARY KEY,
            registration_id VARCHAR,
            client_org_name VARCHAR,
            communication_date DATE,
            posted_date DATE,
            lobbyist_name VARCHAR,
            dpoh_name VARCHAR,
            dpoh_title VARCHAR,
            government_institution VARCHAR
        );
        CREATE TABLE IF NOT EXISTS subject_matters (
            entity_type VARCHAR,
            entity_id VARCHAR,
            subject_text VARCHAR,
            legislative_proposal VARCHAR
        );
        CREATE INDEX IF NOT EXISTS idx_subj_bill ON subject_matters (legislative_proposal);
        CREATE INDEX IF NOT EXISTS idx_comm_date ON communications (communication_date);
        CREATE INDEX IF NOT EXISTS idx_comm_client ON communications (client_org_name);
    """

    REGISTRATION_COLUMNS: ClassVar[list[str]] = [
        "registration_id",
        "registrant_name",
        "client_org_name",
        "type",
        "status",
        "effective_date",
        "posted_date",
    ]

    COMMUNICATION_COLUMNS: ClassVar[list[str]] = [
        "communication_id",
        "registration_id",
        "client_org_name",
        "communication_date",
        "posted_date",
        "lobbyist_name",
        "dpoh_name",
        "dpoh_title",
        "government_institution",
    ]

    SUBJECT_MATTER_COLUMNS: ClassVar[list[str]] = [
        "entity_type",
        "entity_id",
        "subject_text",
        "legislative_proposal",
    ]

    def __init__(self, db_path: str):
        abs_db_path = os.path.abspath(db_path)
        self.db = DuckDBExporter(abs_db_path)
        self.db.execute_schema(self.SCHEMA_SQL)

    def export_registrations(self, registrations: list[Any]) -> int:
        """Transform and export LobbyRegistration records to DuckDB."""
        if not registrations:
            return 0

        reg_tuples = []
        subj_tuples = []

        for reg in registrations:
            data = reg.model_dump() if hasattr(reg, "model_dump") else reg
            reg_id = str(data.get("registration_id") or "")
            if not reg_id:
                continue

            reg_tuples.append(
                (
                    reg_id,
                    data.get("registrant_name"),
                    data.get("client_org_name"),
                    data.get("type"),
                    data.get("status"),
                    clean_date(data.get("effective_date")),
                    clean_date(data.get("posted_date")),
                )
            )

            subjects = data.get("subject_matters") or []
            bills = data.get("legislative_proposals") or []
            for s in subjects:
                subj_tuples.append(("registration", reg_id, s, None))
            for b in bills:
                subj_tuples.append(("registration", reg_id, None, b))

        count = self.db.insert_records("registrations", self.REGISTRATION_COLUMNS, reg_tuples, on_conflict="replace")
        if subj_tuples:
            self.db.insert_records("subject_matters", self.SUBJECT_MATTER_COLUMNS, subj_tuples)
        return count

    def export_communications(self, communications: list[Any]) -> int:
        """Transform and export LobbyCommunication records to DuckDB."""
        if not communications:
            return 0

        comm_tuples = []
        subj_tuples = []

        for comm in communications:
            data = comm.model_dump() if hasattr(comm, "model_dump") else comm
            comm_id = str(data.get("communication_id") or "")
            if not comm_id:
                continue

            comm_tuples.append(
                (
                    comm_id,
                    data.get("registration_id"),
                    data.get("client_org_name"),
                    clean_date(data.get("communication_date")),
                    clean_date(data.get("posted_date")),
                    data.get("lobbyist_name"),
                    data.get("dpoh_name"),
                    data.get("dpoh_title"),
                    data.get("government_institution"),
                )
            )

            subjects = data.get("subject_matters") or []
            bills = data.get("legislative_proposals") or []
            for s in subjects:
                subj_tuples.append(("communication", comm_id, s, None))
            for b in bills:
                subj_tuples.append(("communication", comm_id, None, b))

        count = self.db.insert_records("communications", self.COMMUNICATION_COLUMNS, comm_tuples, on_conflict="replace")
        if subj_tuples:
            self.db.insert_records("subject_matters", self.SUBJECT_MATTER_COLUMNS, subj_tuples)
        return count

    def close(self) -> None:
        """Close database connection."""
        self.db.close()
