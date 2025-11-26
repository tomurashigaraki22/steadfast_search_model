from dotenv import dotenv_values
from urllib.parse import urlparse, unquote
from pymysql.converters import escape_string
import pymysql
import os
import sys

def main():
    env_path = r"c:\Users\emman\OneDrive\Desktop\steadfast_ml\.env"
    cfg = dotenv_values(env_path)
    url = "mysql://root:GsccJaCyYvIPcQtFyRuMTGidlblqhifG@shinkansen.proxy.rlwy.net:52553/railway"
    if url:
        parsed = urlparse(url)
        host = parsed.hostname
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        database = (parsed.path or "/").lstrip("/")
        port = int(parsed.port or 3306)
    else:
        host = cfg.get("MYSQL_HOST")
        user = cfg.get("MYSQL_USER")
        password = cfg.get("MYSQL_ROOT_PASSWORD") or cfg.get("MYSQL_PASSWORD")
        database = cfg.get("MYSQL_DATABASE")
        port = int(cfg.get("MYSQL_PORT") or "3306")
    if not all([host, user, password, database, port]):
        print("Missing database configuration in .env")
        sys.exit(1)
    try:
        conn = pymysql.connect(host=host, user=user, password=password, database=database, port=port, charset="utf8mb4")
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM `products`")
            rows = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]
        def sql_literal(val):
            if val is None:
                return "NULL"
            if isinstance(val, (int, float)):
                return str(val)
            if isinstance(val, bytes):
                return "0x" + val.hex()
            try:
                import datetime
                if isinstance(val, (datetime.date, datetime.datetime, datetime.time)):
                    return "'" + str(val) + "'"
            except Exception:
                pass
            s = escape_string(str(val))
            return "'" + s + "'"
        outfile = os.path.join(os.getcwd(), "product_details.sql")
        with open(outfile, "w", encoding="utf-8") as f:
            for row in rows:
                values = ", ".join(sql_literal(v) for v in row)
                f.write(f"INSERT INTO `products` ({', '.join('`'+c+'`' for c in cols)}) VALUES ({values});\n")
        print(outfile)
    except Exception as e:
        print(str(e))
        sys.exit(1)
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()

