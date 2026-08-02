"""Configuration constants for Lobby Canada crawler."""

LOBBY_CANADA_BASE_URL = "https://lobbycanada.gc.ca"

# Open Canada Open Data Portal Dataset Page URLs
# Updated 2024-06: OCL migrated data from open.canada.ca static CSVs to lobbycanada.gc.ca ZIP archives
REGISTRATIONS_DATASET_URL = "https://open.canada.ca/data/en/dataset/70ef2117-1095-4d77-80eb-b87f2bada2a4"
COMMUNICATIONS_DATASET_URL = "https://open.canada.ca/data/en/dataset/a34eb330-7136-4f5e-9f5f-3ba41df58b06"

# Open Data ZIP downloads from lobbycanada.gc.ca (contain primary + secondary CSV files)
REGISTRATIONS_CSV_URL = "https://lobbycanada.gc.ca/media/zwcjycef/registrations_enregistrements_ocl_cal.zip"
COMMUNICATIONS_CSV_URL = "https://lobbycanada.gc.ca/media/mqbbmaqk/communications_ocl_cal.zip"

# Expected primary key column names in each CSV (used for header validation)
REGISTRATIONS_SENTINEL_COLUMN = "REGID"
COMMUNICATIONS_SENTINEL_COLUMN = "COMCID"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
