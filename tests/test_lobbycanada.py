import os
import tempfile
from unittest.mock import patch

from civican.schemas import LobbyRegistration

from civican.scraper.crawlers.lobbycanada.crawler import LobbyCanadaCrawler
from civican.scraper.crawlers.lobbycanada.parser import extract_bill_references, parse_registration_entry


def test_extract_bill_references():
    text = "Discussions regarding Bill C-11 and Senate Bill S-2 broadcasting policy."
    bills = extract_bill_references(text)
    assert bills == ["C-11", "S-2"]


def test_parse_registration_entry():
    data = {
        "REGID": "REG-123",
        "REGISTRANT_NAME": "John Doe",
        "CLIENT_ORG_NAME": "Acme Corp",
        "SUBJECT_MATTER": "Policy regarding Bill C-25",
    }
    reg = parse_registration_entry(data)
    assert isinstance(reg, LobbyRegistration)
    assert reg.registration_id == "REG-123"
    assert reg.legislative_proposals == ["C-25"]


def test_lobbycanada_crawler_execution_json():
    mock_reg_csv = (
        '"REGID","REGISTRANT_NAME","CLIENT_ORG_NAME","REG_TYPE","REG_STATUS",'
        '"EFFECTIVE_DATE","POSTED_DATE","SUBJECT_MATTER","GOVT_INST_NAME"\n'
        '"REG-1001","Jane Doe","Tech Canada","Corporation","Active",'
        '"2026-01-15","2026-01-16","Bill C-11","ISED"\n'
    )
    mock_comm_csv = (
        '"COMCID","REGID","CLIENT_ORG_NAME","COMM_DATE","POSTED_DATE",'
        '"LOBBYIST_NAME","DPOH_NAME","DPOH_TITLE","GOVT_INST_NAME","SUBJECT_MATTER"\n'
        '"COMM-5001","REG-1001","Tech Canada","2026-02-10","2026-02-12",'
        '"Jane Doe","John Smith","Advisor","ISED","Bill C-11"\n'
    )

    def mock_fetch_open_canada_csv(dataset_url, csv_url, *_args, **_kwargs):
        if "registrations" in csv_url or "c2aa3476" in dataset_url:
            return mock_reg_csv
        return mock_comm_csv

    with tempfile.TemporaryDirectory() as tmpdir:
        crawler = LobbyCanadaCrawler()
        with patch(
            "civican.scraper.crawlers.lobbycanada.crawler.fetch_open_canada_csv", side_effect=mock_fetch_open_canada_csv
        ):
            res = crawler.scrape_data(repo_path=tmpdir, output_format="json")
            assert res.success is True
            assert res.total_scraped == 2
            assert os.path.exists(os.path.join(tmpdir, "registrations"))
            assert os.path.exists(os.path.join(tmpdir, "communications"))


def test_lobbycanada_crawler_execution_duckdb():
    mock_reg_csv = (
        '"REGID","REGISTRANT_NAME","CLIENT_ORG_NAME","REG_TYPE","REG_STATUS",'
        '"EFFECTIVE_DATE","POSTED_DATE","SUBJECT_MATTER","GOVT_INST_NAME"\n'
        '"REG-1001","Jane Doe","Tech Canada","Corporation","Active",'
        '"2026-01-15","2026-01-16","Bill C-11","ISED"\n'
    )
    mock_comm_csv = (
        '"COMCID","REGID","CLIENT_ORG_NAME","COMM_DATE","POSTED_DATE",'
        '"LOBBYIST_NAME","DPOH_NAME","DPOH_TITLE","GOVT_INST_NAME","SUBJECT_MATTER"\n'
        '"COMM-5001","REG-1001","Tech Canada","2026-02-10","2026-02-12",'
        '"Jane Doe","John Smith","Advisor","ISED","Bill C-11"\n'
    )

    def mock_fetch_open_canada_csv(dataset_url, csv_url, *_args, **_kwargs):
        if "registrations" in csv_url or "c2aa3476" in dataset_url:
            return mock_reg_csv
        return mock_comm_csv

    with tempfile.TemporaryDirectory() as tmpdir:
        crawler = LobbyCanadaCrawler()
        with patch(
            "civican.scraper.crawlers.lobbycanada.crawler.fetch_open_canada_csv", side_effect=mock_fetch_open_canada_csv
        ):
            res = crawler.scrape_data(repo_path=tmpdir, output_format="duckdb")
            assert res.success is True
            assert res.total_scraped == 2
            assert os.path.exists(os.path.join(tmpdir, "lobbycanada.duckdb"))
