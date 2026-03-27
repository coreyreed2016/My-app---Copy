from __future__ import annotations

import re
from datetime import timedelta, timezone


NUMBER_PATTERN = re.compile(r"-?\d[\d.,]*")
TIME_INPUT_PATTERN = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")
UTC_MINUS_5 = timezone(timedelta(hours=-5))
FEED_STALE_AFTER_SECONDS = 3.0


def parse_number_token(token: str):
    cleaned = token.strip().replace(" ", "")
    if not cleaned:
        return None

    sign = -1 if cleaned.startswith("-") else 1
    cleaned = cleaned.lstrip("+-")
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None

    if "," not in cleaned and "." not in cleaned:
        try:
            return sign * float(cleaned)
        except ValueError:
            return None

    if "," in cleaned and "." in cleaned:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        normalized = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
        try:
            return sign * float(normalized)
        except ValueError:
            return None

    sep = "," if "," in cleaned else "."
    parts = cleaned.split(sep)
    if not all(part.isdigit() for part in parts):
        return None

    if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
        normalized = "".join(parts)
    elif len(parts) == 2 and len(parts[1]) == 3:
        normalized = "".join(parts)
    else:
        normalized = ".".join(parts)

    try:
        return sign * float(normalized)
    except ValueError:
        return None


def format_number(value):
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        numeric_value = float(value)
    else:
        numeric_value = parse_number_token(str(value))
        if numeric_value is None:
            return "-"
    if numeric_value.is_integer():
        return f"{int(numeric_value):,}"
    return f"{numeric_value:,.6f}".rstrip("0").rstrip(".")


def format_currency(value):
    if value is None:
        return "-"
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"
