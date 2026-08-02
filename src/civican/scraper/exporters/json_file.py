"""JSON File hierarchy exporter."""

import json
import os
from typing import Any

from civican.scraper.exporters.base import BaseExporter


class JsonFileExporter(BaseExporter):
    """Exporter that writes records as individual JSON files in repo directory structure."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.registrations_dir = os.path.join(repo_path, "registrations")
        self.communications_dir = os.path.join(repo_path, "communications")

    def export_registrations(self, registrations: list[Any]) -> int:
        """Export registrations to JSON files under registrations/<id>.json."""
        if not registrations:
            return 0
        os.makedirs(self.registrations_dir, exist_ok=True)
        count = 0
        for reg in registrations:
            data = reg.model_dump() if hasattr(reg, "model_dump") else reg
            reg_id = str(data.get("registration_id") or "")
            if not reg_id:
                continue
            reg_file = os.path.join(self.registrations_dir, f"{reg_id}.json")
            with open(reg_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
            count += 1
        return count

    def export_communications(self, communications: list[Any]) -> int:
        """Export communications to JSON files under communications/YYYY/MM/<id>.json."""
        if not communications:
            return 0
        os.makedirs(self.communications_dir, exist_ok=True)
        count = 0
        for comm in communications:
            data = comm.model_dump() if hasattr(comm, "model_dump") else comm
            comm_id = str(data.get("communication_id") or "")
            if not comm_id:
                continue
            comm_date = str(data.get("communication_date") or "")
            parts = comm_date.split("-") if comm_date else []
            if len(parts) >= 2:
                comm_subdir = os.path.join(self.communications_dir, parts[0], parts[1])
            else:
                comm_subdir = self.communications_dir
            os.makedirs(comm_subdir, exist_ok=True)
            comm_file = os.path.join(comm_subdir, f"{comm_id}.json")
            with open(comm_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
            count += 1
        return count

    def close(self) -> None:
        """Clean up resources if needed."""
        pass
