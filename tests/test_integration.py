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

if __name__ == "__main__":
    unittest.main()
