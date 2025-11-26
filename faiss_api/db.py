import mysql.connector
from typing import Optional, Dict, List
from .config import load_config, parse_mysql_url

def get_connection():
    """
    Returns a MySQL connection using MYSQL_URL from config.
    """
    cfg = load_config()
    url = cfg.get("MYSQL_URL")
    if not url:
        raise RuntimeError("MYSQL_URL not set in environment or .env")
    params = parse_mysql_url(url)
    return mysql.connector.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database=params["database"],
        charset="utf8mb4",
        autocommit=True,
    )

def fetch_product(product_id: int) -> Optional[Dict]:
    """
    Fetches a single product by id as a dict.
    """
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `products` WHERE `id`=%s", (product_id,))
        row = cur.fetchone()
        return row
    finally:
        conn.close()

def fetch_all_products() -> List[Dict]:
    """
    Fetches all products as a list of dicts.
    """
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `products`")
        return cur.fetchall()
    finally:
        conn.close()

