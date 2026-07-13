#!/usr/bin/env python3
import os
import sys

# Add the src folder to path so we can resolve legisinfo_scraper package
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from legisinfo_scraper.cli import main

if __name__ == "__main__":
    main()
