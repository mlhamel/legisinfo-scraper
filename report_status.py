#!/usr/bin/env python3
import sys
import os
import argparse

# Add the src folder to path so we can resolve legisinfo_scraper package
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from legisinfo_scraper.report_status import report_status

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LEGISinfo Scraper Status Reporter")
    parser.add_argument("--repo", required=True, help="Path to the legisinfo data repository")
    args = parser.parse_args()
    
    if not os.path.exists(args.repo):
        print(f"Error: Repository path '{args.repo}' does not exist.")
        sys.exit(1)
        
    report_status(args.repo)
