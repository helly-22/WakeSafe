"""CSV provider (Person A): read an uploaded nightly CSV into NightRecord objects.

`csv_file` is a path to a file, or the CSV text itself when the string contains a line break.
Nothing is written to disk or logged: the file is read once, row contents are never printed,
and error messages name rows and columns only.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from app.models import NightRecord

from .normalize import ProviderDataError, frame_to_nights

MAX_CSV_BYTES = 2_000_000


def load_csv_nights(csv_file: str | None) -> list[NightRecord]:
    if not csv_file:
        raise ProviderDataError("No CSV file was provided. Pass the path to a nightly CSV file.")
    if "\n" in csv_file:
        raw = csv_file.encode("utf-8", errors="replace")
        if len(raw) > MAX_CSV_BYTES:
            raise ProviderDataError(f"The CSV is larger than the {MAX_CSV_BYTES // 1_000_000} MB limit.")
        source: io.StringIO | Path = io.StringIO(csv_file)
    else:
        path = Path(csv_file)
        if not path.is_file():
            raise ProviderDataError("The CSV file could not be found.")
        if path.stat().st_size > MAX_CSV_BYTES:
            raise ProviderDataError(f"The CSV is larger than the {MAX_CSV_BYTES // 1_000_000} MB limit.")
        source = path
    try:
        df = pd.read_csv(source, comment="#")
    except Exception as exc:  # parser messages can quote file content, so report the type only
        raise ProviderDataError(f"The file could not be read as a CSV table ({type(exc).__name__}).") from None
    if df.empty:
        raise ProviderDataError("The CSV has a header but no rows.")
    return frame_to_nights(df, "csv")
