import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from legisinfo_scraper.cli import main as scraper_main
from legisinfo_scraper.report_status import report_status as status_main


def mock_requests_get(url, *_args, **_kwargs):
    class MockResponse:
        def __init__(self, content, text, status_code=200):
            self.content = content.encode("utf-8") if isinstance(content, str) else content
            self.text = text
            self.status_code = status_code

    if "parlsession=all" in url or "parlsession=36-1" in url or "parlsession=45-1" in url:
        xml_content = """<Bills>
          <Bill>
            <ParlSessionCode>45-1</ParlSessionCode>
            <ParlSessionEn>45th Parliament, 1st session</ParlSessionEn>
            <BillNumberFormatted>S-2</BillNumberFormatted>
            <CurrentStatusEn>At consideration in committee in the Senate</CurrentStatusEn>
            <LatestActivityEn>At consideration in committee in the Senate</LatestActivityEn>
            <LongTitleEn>An Act to amend the Safety Board Act</LongTitleEn>
          </Bill>
          <Bill>
            <ParlSessionCode>36-1</ParlSessionCode>
            <ParlSessionEn>36th Parliament, 1st session</ParlSessionEn>
            <BillNumberFormatted>S-2</BillNumberFormatted>
            <CurrentStatusEn>Royal assent received</CurrentStatusEn>
            <LatestActivityEn>Royal assent received</LatestActivityEn>
            <LongTitleEn>An Act to amend the Canadian Transportation Act</LongTitleEn>
          </Bill>
        </Bills>"""
        return MockResponse(xml_content, xml_content)

    if "/bill/45-1/S-2/xml" in url:
        xml_content = """<Bill>
          <NumberCode>S-2</NumberCode>
          <LongTitleEn>An Act to amend the Safety Board Act</LongTitleEn>
          <StatusNameEn>At consideration in committee in the Senate</StatusNameEn>
          <SponsorPersonName>Senator Gold</SponsorPersonName>
          <LatestBillEventTypeName>First Reading</LatestBillEventTypeName>
          <LatestBillEventDateTime>2026-02-27T10:00:00</LatestBillEventDateTime>
          <SenateBillStages>
            <SenateBillStage>
              <BillStageNameEn>First Reading</BillStageNameEn>
              <StateNameEn>Completed</StateNameEn>
              <LastStageEventStartDateTime>2026-02-27T10:00:00</LastStageEventStartDateTime>
            </SenateBillStage>
          </SenateBillStages>
        </Bill>"""
        return MockResponse(xml_content, xml_content)

    if "/bill/36-1/S-2/xml" in url:
        xml_content = """<Bill>
          <NumberCode>S-2</NumberCode>
          <LongTitleEn>An Act to amend the Canadian Transportation Act</LongTitleEn>
          <StatusNameEn>Royal assent received</StatusNameEn>
          <SponsorPersonName>Senator B. Graham</SponsorPersonName>
          <LatestBillEventTypeName>Royal Assent</LatestBillEventTypeName>
          <LatestBillEventDateTime>1998-06-18T00:00:00</LatestBillEventDateTime>
          <SenateBillStages>
            <SenateBillStage>
              <BillStageNameEn>First Reading</BillStageNameEn>
              <StateNameEn>Completed</StateNameEn>
              <LastStageEventStartDateTime>1998-05-28T00:00:00</LastStageEventStartDateTime>
            </SenateBillStage>
          </SenateBillStages>
        </Bill>"""
        return MockResponse(xml_content, xml_content)

    if "/DocumentViewer/en/45-1/bill/S-2/first-reading" in url:
        html_content = """<html><body>
          <div class="publication-tabs">
            <div class="nav-tab"><a href="/DocumentViewer/en/45-1/bill/S-2/first-reading">First Reading</a></div>
          </div>
          <a href="/Content/Bills/451/Government/S-2/S-2_1/S-2_E.xml">XML Link</a>
        </body></html>"""
        return MockResponse(html_content, html_content)

    if "/Content/Bills/451/Government/S-2/S-2_1/S-2_E.xml" in url:
        xml_content = """<Bill>
          <Identification><BillNumber>S-2</BillNumber></Identification>
          <Body><Text>This is the test text of S-2.</Text></Body>
        </Bill>"""
        return MockResponse(xml_content, xml_content)

    if "/DocumentViewer/en/36-1/bill/S-2/first-reading" in url:
        html_content = """<html><body>
          <div class="publication-tabs">
            <div class="nav-tab"><a href="/DocumentViewer/en/36-1/bill/S-2/first-reading">First Reading</a></div>
          </div>
          <div id="publicationContent">
            <p>This is the HTML fallback text of S-2.</p>
          </div>
        </body></html>"""
        return MockResponse(html_content, html_content)

    return MockResponse("", "", 404)


class TestScraperIntegration(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the target data git repository
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = os.path.join(self.test_dir.name, "test_repo")
        os.makedirs(self.repo_path)
        self.cache_path = os.path.join(self.test_dir.name, "cache")
        os.makedirs(self.cache_path)

        # Initialize Git repository
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        # Set local git config for author/email
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo_path, check=True)

    def tearDown(self):
        # Cleanup temporary directory
        self.test_dir.cleanup()

    def test_scrape_single_session_limit(self):
        # Run scraper in-process with patched argv and requests
        args = [
            "scraper.py",
            "--repo",
            self.repo_path,
            "--session",
            "45-1",
            "--limit",
            "2",
            "--cache-dir",
            self.cache_path,
        ]
        with patch("sys.argv", args), patch("requests.get", side_effect=mock_requests_get):
            scraper_main()

        # Assert directories/files were created
        session_dir = os.path.join(self.repo_path, "45-1")
        assert os.path.exists(session_dir)
        assert os.path.exists(os.path.join(session_dir, "README.md"))

        # Assert git commits were created
        git_log = subprocess.run(
            ["git", "log", "--oneline"], cwd=self.repo_path, capture_output=True, text=True, check=True
        )
        commits = git_log.stdout.strip().split("\n")
        assert len(commits) >= 1

        # Check chronological ordering of dates in git history
        git_dates = subprocess.run(
            ["git", "log", "--format=%ad", "--date=iso"], cwd=self.repo_path, capture_output=True, text=True, check=True
        )
        dates = [d for d in git_dates.stdout.strip().split("\n") if d]
        dates.reverse()

        for i in range(len(dates) - 1):
            assert dates[i] <= dates[i + 1]

    def test_status_reporter(self):
        # Create a mock session index
        session_code = "45-1"
        session_dir = os.path.join(self.repo_path, session_code)
        os.makedirs(session_dir, exist_ok=True)
        readme_path = os.path.join(session_dir, "README.md")

        # Write a mock index showing 1 bill is scraped
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(
                "# Parliament Session 45-1 Bills Index\n\n"
                "| Bill | Title | Current Status | Latest Activity | Downloaded Stages | Last Checked |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| [S-2](...) | Title | Status | Activity | `first-reading` | 2026-07-09 |\n"
            )

        f = io.StringIO()
        with redirect_stdout(f), patch("requests.get", side_effect=mock_requests_get):
            status_main(self.repo_path)

        output = f.getvalue()
        assert "45-1" in output
        assert "Incomplete" in output
        assert "Session" in output
        assert "Total Bills" in output
        assert "Scraped Bills" in output
        assert "Status" in output

    def test_html_fallback(self):
        # Run scraper targeting session 36-1 with limit 3 (which will fetch HTML-only bills)
        args = [
            "scraper.py",
            "--repo",
            self.repo_path,
            "--session",
            "36-1",
            "--limit",
            "3",
            "--cache-dir",
            self.cache_path,
        ]
        with patch("sys.argv", args), patch("requests.get", side_effect=mock_requests_get):
            scraper_main()

        bills_dir = os.path.join(self.repo_path, "36-1", "bills")
        assert os.path.exists(bills_dir)

        scraped_bills = os.listdir(bills_dir)
        has_text_bill = False
        for b in scraped_bills:
            xml_p = os.path.join(bills_dir, b, "bill_text.xml")
            md_p = os.path.join(bills_dir, b, "bill_text.md")
            if os.path.exists(xml_p) and os.path.exists(md_p):
                has_text_bill = True
                with open(xml_p, encoding="utf-8") as f:
                    xml_content = f.read()
                    assert "HTML Fallback" in xml_content
                with open(md_p, encoding="utf-8") as f:
                    md_content = f.read()
                    assert len(md_content) > 10
                break
        assert has_text_bill

    def test_autosquash_rewriting(self):
        # 1. Run scraper first time to create initial history and cache
        args = [
            "scraper.py",
            "--repo",
            self.repo_path,
            "--session",
            "45-1",
            "--limit",
            "2",
            "--cache-dir",
            self.cache_path,
        ]
        with patch("sys.argv", args), patch("requests.get", side_effect=mock_requests_get):
            scraper_main()

        # Check commit count before update
        git_log = subprocess.run(
            ["git", "log", "--oneline"], cwd=self.repo_path, capture_output=True, text=True, check=True
        )
        commits_before = git_log.stdout.strip().split("\n")
        num_commits_before = len(commits_before)

        # Check content of bill_text.md before update
        bill_md_path = os.path.join(self.repo_path, "45-1", "bills", "S-2", "bill_text.md")
        with open(bill_md_path, encoding="utf-8") as f:
            content_before = f.read().strip()
        assert "This is the test text of S-2." in content_before

        # Clear cache so it fetches the new mocked XML content
        shutil.rmtree(self.cache_path)
        os.makedirs(self.cache_path)

        # 2. Custom mock response routing to intercept the S-2 XML link
        def custom_mock_get(url, *a, **kw):
            class MockResponse:
                def __init__(self, content, text, status_code=200):
                    self.content = content.encode("utf-8") if isinstance(content, str) else content
                    self.text = text
                    self.status_code = status_code

            if "/Content/Bills/451/Government/S-2/S-2_1/S-2_E.xml" in url:
                xml_content = """<Bill>
                  <Identification><BillNumber>S-2</BillNumber></Identification>
                  <Body><Text>This is the UPDATED text of S-2.</Text></Body>
                </Bill>"""
                return MockResponse(xml_content, xml_content)
            return mock_requests_get(url, *a, **kw)

        # 3. Run scraper second time with --force
        args_force = [
            "scraper.py",
            "--repo",
            self.repo_path,
            "--session",
            "45-1",
            "--limit",
            "2",
            "--force",
            "--cache-dir",
            self.cache_path,
        ]
        with patch("sys.argv", args_force), patch("requests.get", side_effect=custom_mock_get):
            scraper_main()

        # Check content after update
        with open(bill_md_path, encoding="utf-8") as f:
            content_after = f.read().strip()
        assert "This is the UPDATED text of S-2." in content_after

        # Check commit count after update: should be identical because it squashed!
        git_log_after = subprocess.run(
            ["git", "log", "--oneline"], cwd=self.repo_path, capture_output=True, text=True, check=True
        )
        commits_after = git_log_after.stdout.strip().split("\n")
        num_commits_after = len(commits_after)

        assert num_commits_after == num_commits_before


if __name__ == "__main__":
    unittest.main()
