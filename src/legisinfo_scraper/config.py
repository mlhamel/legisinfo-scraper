# Base URL for LEGISinfo
LEGISINFO_BASE = "https://www.parl.ca/legisinfo"
DOC_VIEWER_BASE = "https://www.parl.ca/DocumentViewer"

# Stage priority mapping for sequential commits
STAGE_DETAILS = {
    "first-reading": ("First Reading", 1),
    "second-reading": ("Second Reading", 2),
    "committee": ("Committee stage", 3),
    "third-reading": ("Third Reading", 4),
    "royal-assent": ("Royal Assent", 5)
}
