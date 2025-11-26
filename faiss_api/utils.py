import os
import re
from typing import List, Dict
from .config import SQL_DUMP_PATH

def _split_sql_values(values_str: str) -> List[str]:
    """
    Splits a VALUES(...) list into individual SQL literals, respecting quotes and escapes.
    """
    out, buf, in_str, esc = [], [], False, False
    for ch in values_str:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\":
            buf.append(ch)
            esc = True
            continue
        if ch == "'" and not in_str:
            in_str = True
            buf.append(ch)
            continue
        if ch == "'" and in_str:
            in_str = False
            buf.append(ch)
            continue
        if ch == "," and not in_str:
            out.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf).strip())
    return out

def _sql_literal_to_python(token: str):
    """
    Converts a SQL literal token to Python value.
    """
    if token.upper() == "NULL":
        return None
    if token.startswith("'") and token.endswith("'"):
        s = token[1:-1]
        s = s.replace("\\'", "'")
        s = s.replace("\\\\", "\\")
        return s
    try:
        if "." in token:
            return float(token)
        return int(token)
    except Exception:
        return token

def parse_product_rows_from_sql() -> List[Dict]:
    """
    Parses INSERT INTO `products` ... VALUES (...) lines from product_details.sql.
    Returns list of dict rows.
    """
    if not os.path.exists(SQL_DUMP_PATH):
        return []
    rows: List[Dict] = []
    with open(SQL_DUMP_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("INSERT INTO `products`"):
                continue
            m = re.search(r"INSERT INTO `products` \((.*?)\) VALUES \((.*)\);$", line)
            if not m:
                continue
            columns_str, values_str = m.group(1), m.group(2)
            cols = [c.strip().strip("`") for c in columns_str.split(",")]
            tokens = _split_sql_values(values_str)
            pyvals = [_sql_literal_to_python(t) for t in tokens]
            if len(cols) != len(pyvals):
                continue
            row = {c: v for c, v in zip(cols, pyvals)}
            rows.append(row)
    return rows

