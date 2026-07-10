import os
import sys
import shutil
import tempfile
import unittest
import subprocess

class TestScraperIntegration(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the target data git repository
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = os.path.join(self.test_dir.name, "test_repo")
        os.makedirs(self.repo_path)
        
        # Initialize Git repository
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        # Set local git config for author/email
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo_path, check=True)
        
        # Path to scraper.py
        self.scraper_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scraper.py"))

    def tearDown(self):
        # Cleanup temporary directory
        self.test_dir.cleanup()

    def test_scrape_single_session_limit(self):
        # Run scraper via subprocess
        cmd = [
            sys.executable,
            self.scraper_path,
            "--repo", self.repo_path,
            "--session", "45-1",
            "--limit", "2"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Assert the command succeeded
        self.assertEqual(result.returncode, 0, f"Scraper failed with: {result.stderr}\nOutput: {result.stdout}")
        
        # Assert directories/files were created
        session_dir = os.path.join(self.repo_path, "45-1")
        self.assertTrue(os.path.exists(session_dir))
        self.assertTrue(os.path.exists(os.path.join(session_dir, "README.md")))
        
        # Assert git commits were created
        git_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        # Should have at least one commit
        commits = git_log.stdout.strip().split("\n")
        self.assertGreaterEqual(len(commits), 1)
        
        # Check chronological ordering of dates in git history
        git_dates = subprocess.run(
            ["git", "log", "--format=%ad", "--date=iso"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        dates = [d for d in git_dates.stdout.strip().split("\n") if d]
        # Since git log is newest-first, we reverse it to get oldest-first
        dates.reverse()
        
        # Verify dates are in non-decreasing chronological order
        for i in range(len(dates) - 1):
            self.assertLessEqual(dates[i], dates[i+1], f"Commits are not in chronological order: {dates}")

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
                "| [S-1](...) | Title | Status | Activity | `first-reading` | 2026-07-09 |\n"
            )
            
        # Run report_status.py via subprocess
        status_script = os.path.join(os.path.dirname(self.scraper_path), "report_status.py")
        cmd = [
            sys.executable,
            status_script,
            "--repo", self.repo_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 0)
        # S-1 has no bill_text.xml on disk, so 45-1 should be "Incomplete"
        self.assertIn("45-1", result.stdout)
        self.assertIn("Incomplete", result.stdout)
        self.assertIn("Session", result.stdout)
        self.assertIn("Total Bills", result.stdout)
        self.assertIn("Scraped Bills", result.stdout)
        self.assertIn("Status", result.stdout)

    def test_html_fallback(self):
        # Run scraper targeting session 36-1 with limit 3 (which will fetch HTML-only bills)
        cmd = [
            sys.executable,
            self.scraper_path,
            "--repo", self.repo_path,
            "--session", "36-1",
            "--limit", "3"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Scraper failed with: {result.stderr}\nOutput: {result.stdout}")
        
        bills_dir = os.path.join(self.repo_path, "36-1", "bills")
        self.assertTrue(os.path.exists(bills_dir))
        
        # Verify that we have at least one bill with bill_text.md and bill_text.xml
        scraped_bills = os.listdir(bills_dir)
        has_text_bill = False
        for b in scraped_bills:
            xml_p = os.path.join(bills_dir, b, "bill_text.xml")
            md_p = os.path.join(bills_dir, b, "bill_text.md")
            if os.path.exists(xml_p) and os.path.exists(md_p):
                has_text_bill = True
                with open(xml_p, "r", encoding="utf-8") as f:
                    xml_content = f.read()
                    self.assertIn("HTML Fallback", xml_content)
                with open(md_p, "r", encoding="utf-8") as f:
                    md_content = f.read()
                    self.assertGreater(len(md_content), 100)
                    self.assertIn("Bill", md_content)
                break
        self.assertTrue(has_text_bill, "None of the scraped 36-1 bills got populated with bill_text.md via HTML Fallback")

if __name__ == "__main__":
    unittest.main()
