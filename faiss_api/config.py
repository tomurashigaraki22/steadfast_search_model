import os
from urllib.parse import urlparse
from dotenv import dotenv_values

# Use relative paths as requested
BASE_DIR = "."
ENV_PATH = os.path.join(BASE_DIR, ".env")
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_PATH = os.path.join(DATA_DIR, "products_index.bin")
MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
SQL_DUMP_PATH = os.path.join(BASE_DIR, "product_details.sql")

def load_config():
    """
    Loads configuration from OS environment and .env file.
    Returns a dict with MYSQL_URL if available.
    """
    env = {}
    env.update(dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {})
    env.update(os.environ)
    url = env.get("MYSQL_URL") or env.get("DATABASE_URL")
    return {"MYSQL_URL": url}

def parse_mysql_url(url: str):
    """
    Parses a MySQL URL into connection parameters for mysql-connector-python.
    """
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": parsed.username or "",
        "password": parsed.password or "",
        "database": (parsed.path or "/").lstrip("/"),
    }

