# LEGISinfo Git Scraper

A Python utility to scrape Canadian parliamentary bills and laws from the LEGISinfo API and document viewer, converting updates into Git commits in a separate data repository.

## Installation

You can run `legisinfo-scraper` as a command-line tool directly:

### Running directly (via uvx)
To run the scraper without installing it locally:
```bash
uvx --from git+https://github.com/mlhamel/legisinfo-scraper.git legisinfo-scraper --repo /path/to/legisinfo.git --session 45-1
```

### Installing globally (via uv)
```bash
uv tool install git+https://github.com/mlhamel/legisinfo-scraper.git
```

### Installing from PyPI (once published)
```bash
uv tool install legisinfo-scraper
```

## Usage

Once installed, the CLI tool `legisinfo-scraper` will be available directly:
```bash
legisinfo-scraper --repo /path/to/legisinfo.git --session 45-1
```

To scrape all historical legislative data across all sessions:
```bash
legisinfo-scraper --repo /path/to/legisinfo.git --session all
```

### Script Workflow
1. Downloads the active session bills list in XML format.
2. Identifies all bills and crawls their detailed status and publications.
3. Downloads the bill metadata XML and legislative text drafts.
4. Updates the target directory.
5. Performs git diff analysis and commits updates with detailed messages.
