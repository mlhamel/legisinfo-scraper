"""Unit tests for generic and domain exporter modules."""

import os
import tempfile

import pytest
from civican.schemas import LobbyCommunication, LobbyRegistration

from civican.scraper.crawlers.lobbycanada.exporter import LobbyCanadaDuckDBExporter
from civican.scraper.exporters import HAS_DUCKDB, DuckDBExporter, JsonFileExporter


def test_json_file_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = JsonFileExporter(repo_path=tmpdir)

        reg = LobbyRegistration(
            registration_id="REG-1001",
            registrant_name="Jane Doe",
            client_org_name="Tech Canada",
            type="Corporation",
            status="Active",
            effective_date="2026-01-15",
            posted_date="2026-01-16",
            subject_matters=["Broadcasting policy"],
            legislative_proposals=["C-11"],
            government_institutions=["ISED"],
        )

        comm = LobbyCommunication(
            communication_id="COMM-5001",
            registration_id="REG-1001",
            client_org_name="Tech Canada",
            communication_date="2026-02-10",
            posted_date="2026-02-12",
            lobbyist_name="Jane Doe",
            dpoh_name="John Smith",
            dpoh_title="Advisor",
            government_institution="ISED",
            subject_matters=["Broadcasting policy"],
            legislative_proposals=["C-11"],
        )

        count_regs = exporter.export_registrations([reg])
        assert count_regs == 1
        assert os.path.exists(os.path.join(tmpdir, "registrations", "REG-1001.json"))

        count_comms = exporter.export_communications([comm])
        assert count_comms == 1
        assert os.path.exists(os.path.join(tmpdir, "communications", "2026", "02", "COMM-5001.json"))


@pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb dependency not installed")
def test_generic_duckdb_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_generic.duckdb")
        exporter = DuckDBExporter(db_path=db_path)

        exporter.execute_schema("CREATE TABLE sample (id INT PRIMARY KEY, name VARCHAR);")
        inserted = exporter.insert_records("sample", ["id", "name"], [(1, "Test Item 1"), (2, "Test Item 2")])
        assert inserted == 2

        exporter.close()
        assert os.path.exists(db_path)


@pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb dependency not installed")
def test_lobbycanada_duckdb_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_lobby.duckdb")
        exporter = LobbyCanadaDuckDBExporter(db_path=db_path)

        reg = LobbyRegistration(
            registration_id="REG-2001",
            registrant_name="Alice Smith",
            client_org_name="Energy Corp",
            type="Corporation",
            status="Active",
            effective_date="2026-03-01",
            posted_date="2026-03-02",
            subject_matters=["Clean Energy"],
            legislative_proposals=["C-50"],
            government_institutions=["NRCan"],
        )

        comm = LobbyCommunication(
            communication_id="COMM-6001",
            registration_id="REG-2001",
            client_org_name="Energy Corp",
            communication_date="2026-03-15",
            posted_date="2026-03-16",
            lobbyist_name="Alice Smith",
            dpoh_name="Bob Jones",
            dpoh_title="Director",
            government_institution="NRCan",
            subject_matters=["Clean Energy"],
            legislative_proposals=["C-50"],
        )

        count_regs = exporter.export_registrations([reg])
        assert count_regs == 1

        count_comms = exporter.export_communications([comm])
        assert count_comms == 1

        exporter.close()
        assert os.path.exists(db_path)
