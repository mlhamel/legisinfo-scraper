# DuckDB Exporter Plan for `civican-scraper`

> [!NOTE]
> This plan outlines adding an optional DuckDB output exporter to `civican-scraper`. It allows crawlers like `lobbycanada` to stream scraped records into a high-performance, single-file DuckDB database (`lobbycanada.duckdb`), while keeping DuckDB as an optional dependency that doesn't impact lightweight crawlers.

---

## 1. Optional Dependency Specification (`pyproject.toml`)

To ensure DuckDB is not required for lightweight usage or other crawlers, it is added as an optional extra in `civican-scraper`:

```toml
[project.optional-dependencies]
duckdb = [
    "duckdb>=0.10.0",
]
all = [
    "duckdb>=0.10.0",
]
```

Users or repositories needing DuckDB support install the package with extras:
```bash
uv sync --extra duckdb
# or
pip install civican-scraper[duckdb]
```

---

## 2. Modular Exporter Architecture & Separation of Concerns

We decouple generic DuckDB database mechanics from crawler-specific domain logic:

```
src/civican/scraper/
├── exporters/
│   ├── __init__.py
│   ├── base.py       # Abstract BaseExporter interface
│   ├── json_file.py  # Standard JSON file hierarchy exporter
│   └── duckdb.py     # Generic, domain-agnostic DuckDB connection & batch insert helper
└── crawlers/
    └── lobbycanada/
        ├── crawler.py
        ├── exporter.py # Lobby Canada specific DuckDB exporter & SQL DDL schema
        └── parser.py
```

### Generic Exporter Layer (`civican.scraper.exporters.duckdb`)
* Completely agnostic to Lobby Canada, LEGISinfo, or any specific domain.
* Handles connection lifecycle (`duckdb.connect`), DDL execution (`execute_schema`), and generic batch inserts (`insert_records`, `insert_dicts`).
* Verifies `duckdb` module presence and raises actionable `ImportError` if missing.

### Domain Exporter Layer (`civican.scraper.crawlers.lobbycanada.exporter`)
* Subclasses `BaseExporter` and wraps `DuckDBExporter`.
* Defines domain tables (`registrations`, `communications`, `subject_matters`) and SQL DDL schemas.
* Transforms domain Pydantic models (`LobbyRegistration`, `LobbyCommunication`) into row tuples.

---

## 3. Database Schema Design (`lobbycanada.duckdb`)

DuckDB schema normalized for fast SQL analytical cross-referencing:

```sql
-- Primary Registrations Table
CREATE TABLE IF NOT EXISTS registrations (
    registration_id VARCHAR PRIMARY KEY,
    registrant_name VARCHAR,
    client_org_name VARCHAR,
    type VARCHAR,
    status VARCHAR,
    effective_date DATE,
    posted_date DATE
);

-- Primary Communication Reports Table
CREATE TABLE IF NOT EXISTS communications (
    communication_id VARCHAR PRIMARY KEY,
    registration_id VARCHAR,
    client_org_name VARCHAR,
    communication_date DATE,
    posted_date DATE,
    lobbyist_name VARCHAR,
    dpoh_name VARCHAR,
    dpoh_title VARCHAR,
    government_institution VARCHAR
);

-- Relational Subject Matters & Bill References Table
CREATE TABLE IF NOT EXISTS subject_matters (
    entity_type VARCHAR,          -- 'registration' or 'communication'
    entity_id VARCHAR,            -- registration_id or communication_id
    subject_text VARCHAR,         -- Full subject description
    legislative_proposal VARCHAR  -- Extracted bill number (e.g. 'C-11', 'S-2')
);

-- Index for instant bill lookups
CREATE INDEX IF NOT EXISTS idx_subj_bill ON subject_matters (legislative_proposal);
CREATE INDEX IF NOT EXISTS idx_comm_date ON communications (communication_date);
CREATE INDEX IF NOT EXISTS idx_comm_client ON communications (client_org_name);
```

---

## 4. Crawler & CLI Integration

### CLI Flags (`civican-scraper lobbycanada`)
Add `--format` and `--db-path` arguments to the CLI:

* `--format` (choices: `json`, `duckdb`, `all`, default: `json`)
* `--db-path` (default: `<repo_path>/lobbycanada.duckdb`)

### Makefile Support in `lobbycanada`
```makefile
FORMAT ?= json
DB_PATH ?= lobbycanada.duckdb

scrape:
	uv run --extra duckdb -- civican-scraper lobbycanada --repo $$(pwd) --format $(FORMAT) --db-path $(DB_PATH)
```

---

## 5. Phased Implementation Roadmap

| Phase | Tasks | Status |
| :--- | :--- | :--- |
| **Phase 1** | Add `duckdb` optional dependency and implement generic `DuckDBExporter` + domain `LobbyCanadaDuckDBExporter`. | **COMPLETE** |
| **Phase 2** | Integrate `LobbyCanadaDuckDBExporter` into `LobbyCanadaCrawler` and CLI options (`--format`, `--db-path`). | **PENDING** |
| **Phase 3** | Update unit tests with mock DuckDB connections and verify end-to-end extraction to `.duckdb` files. | **PENDING** |
| **Phase 4** | Update `lobbycanada` repository `Makefile` and `README.md` with SQL querying documentation. | **PENDING** |
