"""
Thread-safe CSV append utility for evaluation results.

Creates files with headers if they don't exist; otherwise appends rows.
Uses per-file locks so concurrent writes to different CSV files do not block each other.
"""

import csv
import threading
from pathlib import Path
from typing import Any


class CSVWriter:
    """Thread-safe CSV writer that appends rows and creates files with headers when needed."""

    _locks: dict[Path, threading.Lock] = {}
    _locks_mutex = threading.Lock()

    def _get_lock(self, path: Path) -> threading.Lock:
        with self._locks_mutex:
            if path not in self._locks:
                self._locks[path] = threading.Lock()
            return self._locks[path]

    def append_row(self, filepath: Path | str, row_dict: dict[str, Any]) -> None:
        """
        Append a row to the CSV file. Creates the file with headers if it doesn't exist.

        Args:
            filepath: Path to the CSV file.
            row_dict: Dictionary of column -> value. Keys become headers on first write.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with self._get_lock(path):
            file_exists = path.exists()

            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=row_dict.keys())

                if not file_exists:
                    writer.writeheader()

                writer.writerow(row_dict)
