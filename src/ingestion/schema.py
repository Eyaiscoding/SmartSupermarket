"""Shared CSV naming helpers; no imputation of market or temperature readings."""

import unicodedata
from pathlib import Path


def normalize_column(value: str) -> str:
    return "_".join(
        "".join(
            c
            for c in unicodedata.normalize("NFKD", value.strip().lower())
            if not unicodedata.combining(c)
        ).split()
    )


def resolve_csv(path: str | Path) -> Path:
    """Accept Unicode paths, including canonically equivalent accented names."""
    path = Path(path)
    if path.is_file():
        return path
    matches = [
        p
        for p in path.parent.glob("*.csv")
        if normalize_column(p.name) == normalize_column(path.name)
    ]
    if len(matches) == 1:
        return matches[0]
    if path.name == "dataset_modified.csv":
        alternate = path.with_name("dataset_modifié.csv")
        if alternate.is_file():
            return alternate
    raise FileNotFoundError(f"CSV not found: {path}")
