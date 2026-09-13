"""
data_logger.py
---------------
Thread-safe CSV logger used for:
  1. master frame log   (every camera frame, with timestamp + frame index)
  2. sensor log          (every sensor reading, with timestamp)

Every row is timestamped with the SAME clock (time.time()) as the video
frames, so cameras and sensors can be re-synchronized during analysis
just by matching timestamps.
"""

import csv
import os
import threading


class CSVLogger:
    def __init__(self, filepath, fieldnames):
        self.filepath = filepath
        self.fieldnames = fieldnames
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self._file = open(filepath, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=fieldnames)
        self._writer.writeheader()
        self._file.flush()

    def log(self, row: dict):
        with self._lock:
            # only keep known fields; fill missing with blank
            clean_row = {k: row.get(k, "") for k in self.fieldnames}
            self._writer.writerow(clean_row)
            self._file.flush()

    def close(self):
        with self._lock:
            self._file.close()
