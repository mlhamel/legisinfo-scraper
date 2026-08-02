from abc import ABC, abstractmethod
from typing import Any

from civican.schemas import ScrapeResult


class BaseCrawler(ABC):
    """Abstract Base Class for all Civican source crawlers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data source (e.g. 'legisinfo')."""
        pass

    @abstractmethod
    def scrape_bill(
        self,
        session: str,
        bill_number: str,
        cache_bill_dir: str,
        repo_path: str,
        already_downloaded_stages: set[str],
        dry_run: bool = False,
        cache_dir: str | None = None,
    ) -> ScrapeResult:
        """Scrape data for a single bill / item into cache and return pending commits."""
        pass

    @abstractmethod
    def report_status(self, repo_path: str) -> Any:
        """Report synchronization status between upstream source and data repository."""
        pass
