"""
Thread-safe CSV append utility for evaluation results.

Creates files with headers if they don't exist; otherwise appends rows.
Uses a threading lock to prevent concurrent writes from corrupting files.
"""

import csv
import threading
from pathlib import Path
from typing import Any


class CSVWriter:
    """Thread-safe CSV writer that appends rows and creates files with headers when needed."""

    _lock = threading.Lock()

    def append_row(self, filepath: Path | str, row_dict: dict[str, Any]) -> None:
        """
        Append a row to the CSV file. Creates the file with headers if it doesn't exist.

        Args:
            filepath: Path to the CSV file.
            row_dict: Dictionary of column -> value. Keys become headers on first write.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            file_exists = path.exists()

            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=row_dict.keys())

                if not file_exists:
                    writer.writeheader()

                writer.writerow(row_dict)
