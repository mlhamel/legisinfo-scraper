# LEGISinfo Git Scraper

A Python utility to scrape Canadian parliamentary bills and laws from the LEGISinfo API and document viewer, converting updates into Git commits in a separate data repository.

## Installation and Usage

This project uses `uv` for dependency management. You do not need to manually create a virtual environment or run pip.

To run the scraper:
```bash
uv run scraper.py --repo /path/to/legisinfo.git --session 45-1
```

`uv` will automatically set up a virtual environment, install the dependencies from `pyproject.toml`, and run the scraper.

### Script Workflow
1. Downloads the active session bills list in XML format.
2. Identifies all bills and crawls their detailed status and publications.
3. Downloads the bill metadata XML and legislative text drafts.
4. Updates the target directory.
5. Performs git diff analysis and commits updates with detailed messages.
