"""Minimal, dependency-free loading for this repository's host-side scripts.

Docker Compose reads ``.env`` automatically, while a command such as
``python3 scripts/load_m5_forecast.py`` does not.  The M5 scripts use this
helper before importing backend configuration so the same local credentials
work in both paths. Explicit environment variables always win.
"""

import os
import re
from pathlib import Path


ENVIRONMENT_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_quoted_value(value: str, quote: str, line_number: int, path: Path) -> str:
    """Parse a quoted dotenv value without evaluating shell expressions.

    Compose-style database passwords commonly need literal spaces, hashes, or
    quotes.  Double quotes handle the usual escaped quote, slash, newline,
    carriage-return, and tab forms.  Single quotes remain literal except for
    an escaped single quote, which keeps a password such as ``it's-safe``
    expressible without shell evaluation.
    """

    characters = []
    index = 1
    double_quote_escapes = {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "\\": "\\",
        '"': '"',
    }
    while index < len(value):
        character = value[index]
        if character == quote:
            trailing = value[index + 1 :].strip()
            if trailing and not trailing.startswith("#"):
                raise ValueError(
                    f"Unexpected text after quoted value in {path} line {line_number}"
                )
            return "".join(characters)
        if character != "\\":
            characters.append(character)
            index += 1
            continue
        if index + 1 == len(value):
            raise ValueError(f"Unterminated quoted value in {path} line {line_number}")
        escaped = value[index + 1]
        if quote == '"':
            characters.append(double_quote_escapes.get(escaped, f"\\{escaped}"))
        elif escaped == "'":
            characters.append("'")
        else:
            characters.extend(("\\", escaped))
        index += 2
    raise ValueError(f"Unterminated quoted value in {path} line {line_number}")


def _parse_value(raw_value: str, line_number: int, path: Path) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        return _parse_quoted_value(value, value[0], line_number, path)
    for index, character in enumerate(value):
        if character == "#" and index > 0 and value[index - 1].isspace():
            return value[:index].rstrip()
    return value


def load_project_env(root: Path) -> Path | None:
    """Load ``root/.env`` without overriding the caller's environment."""

    path = root / ".env"
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"Project environment path is not a regular file: {path}")

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not ENVIRONMENT_KEY.fullmatch(key):
            raise ValueError(f"Invalid environment assignment in {path} line {line_number}")
        os.environ.setdefault(key, _parse_value(raw_value, line_number, path))
    return path
