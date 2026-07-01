# LEGISinfo Git Tracker Design Document

This document outlines the architecture and execution plan for the LEGISinfo scraper and Git database.

## Architecture

- **Scraper codebase**: Python-based CLI script (`scraper.py`) that queries the official XML APIs of the Parliament of Canada, crawls DocumentViewer HTML to find text downloads, writes them to a formatted directory layout, and stages/commits updates.
- **Git database**: Separate target repository (`legisinfo`) containing the raw XMLs, formatted summaries, and draft revisions of bills over time.

## Data Directory Layout

```
legisinfo/
  45-1/
    bills/
      S-2/
        metadata.xml      # Full detailed metadata from LEGISinfo XML API
        summary.md        # Human-readable summary of status and milestones
        text_drafts/      # Draft versions of the bill at different stages
          first-reading.xml
          third-reading.xml
```
