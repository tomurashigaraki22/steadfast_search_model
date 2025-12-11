import mysql.connector
import json
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

def _loads(val, fallback):
    try:
        return json.loads(val) if val else fallback
    except Exception:
        return fallback

def _compute_stock(product: Dict, variations: List[Dict]):
    base_qty = int(product.get("stock_quantity") or 0)
    var_qty = 0
    for v in variations:
        try:
            var_qty += int(v.get("quantity") or 0)
        except Exception:
            continue
    total = base_qty + var_qty
    status = "in_stock" if total > 0 else "out_of_stock"
    return total, status

def fetch_product(product_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM products WHERE id = %s AND is_deleted = 0", (product_id,))
        product = cur.fetchone()
        if not product:
            return None

        cur.execute("SELECT name FROM categories WHERE id = %s AND is_deleted = 0", (product.get("category"),))
        cat_row = cur.fetchone()
        category_name = (cat_row.get("name") if isinstance(cat_row, dict) else None) if cat_row else None

        cur.execute(
            """
            SELECT v.id, v.variation, v.price, v.quantity,
                   COALESCE(v.price, p.price) AS effective_price
            FROM variations v
            JOIN products p ON p.id = v.product_id
            WHERE v.product_id = %s
            ORDER BY v.id
            """,
            (product_id,),
        )
        variations_rows = cur.fetchall() or []
        formatted_variations = []
        for v in variations_rows:
            formatted_variations.append({
                "id": v.get("id") if isinstance(v, dict) else None,
                "variation": v.get("variation") if isinstance(v, dict) else None,
                "price": (float(v.get("price")) if isinstance(v, dict) and v.get("price") is not None else None),
                "effective_price": float(v.get("effective_price")) if isinstance(v, dict) and v.get("effective_price") is not None else None,
                "quantity": v.get("quantity") if isinstance(v, dict) else None,
            })

        raw_sub_ids = _loads(product.get("sub_categories"), [])
        active_sub_ids: List[int] = []
        if isinstance(raw_sub_ids, list) and raw_sub_ids:
            try:
                placeholders = ",".join(["%s"] * len(raw_sub_ids))
                cur.execute(
                    f"""
                    SELECT id FROM sub_categories
                    WHERE id IN ({placeholders}) AND is_deleted = 0
                    """,
                    tuple(raw_sub_ids),
                )
                allowed_rows = cur.fetchall() or []
                allowed = {r["id"] if isinstance(r, dict) else r[0] for r in allowed_rows}
                active_sub_ids = [sid for sid in raw_sub_ids if sid in allowed]
            except Exception:
                active_sub_ids = raw_sub_ids

        computed_qty, computed_status = _compute_stock(product, formatted_variations)

        formatted_product = {
            "productId": product.get("id"),
            "name": product.get("name"),
            "price": float(product.get("price")) if product.get("price") is not None else None,
            "effective_price": float(product.get("price")) if product.get("price") is not None else None,
            "discount_price": float(product.get("discount_price")) if product.get("discount_price") is not None else None,
            "description": product.get("description"),
            "category_id": product.get("category"),
            "category": category_name,
            "sub_category": active_sub_ids,
            "image_urls": _loads(product.get("image_urls"), []),
            "videos": _loads(product.get("videos"), []),
            "rating": float(product.get("rating")) if product.get("rating") is not None else None,
            "review_count": product.get("review_count"),
            "highlights": _loads(product.get("highlights"), []),
            "specifications": _loads(product.get("specifications"), {}),
            "whats_in_box": _loads(product.get("whats_in_box"), []),
            "stock_quantity": product.get("stock_quantity"),
            "stock_status": product.get("stock_status"),
            "computed_total_stock": computed_qty,
            "computed_stock_status": computed_status,
            "is_variable_product": bool(product.get("is_variable_product")),
            "product_code": product.get("product_code"),
            "total_sold": product.get("total_sold"),
            "created_at": product.get("created_at").isoformat() if product.get("created_at") else None,
            "updated_at": product.get("updated_at").isoformat() if product.get("updated_at") else None,
            "variations": formatted_variations,
        }

        return formatted_product
    finally:
        conn.close()

def fetch_all_products() -> List[Dict]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT p.*, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON p.category = c.id
            WHERE p.is_deleted = 0
            """
        )
        rows = cur.fetchall() or []

        ids = [r.get("id") for r in rows if isinstance(r, dict) and r.get("id") is not None]
        vars_by_product: Dict[int, List[Dict]] = {}
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"""
                SELECT v.id, v.product_id, v.variation, v.price, v.quantity,
                       COALESCE(v.price, p.price) AS effective_price
                FROM variations v
                JOIN products p ON p.id = v.product_id
                WHERE v.product_id IN ({placeholders})
                ORDER BY v.product_id, v.id
                """,
                tuple(ids),
            )
            for v in cur.fetchall() or []:
                pid = v.get("product_id") if isinstance(v, dict) else None
                if pid is None:
                    continue
                vars_by_product.setdefault(pid, []).append({
                    "id": v.get("id"),
                    "variation": v.get("variation"),
                    "price": float(v.get("price")) if v.get("price") is not None else None,
                    "effective_price": float(v.get("effective_price")) if v.get("effective_price") is not None else None,
                    "quantity": v.get("quantity"),
                })

        formatted: List[Dict] = []
        for p in rows:
            vlist = vars_by_product.get(p.get("id"), [])
            computed_qty, computed_status = _compute_stock(p, vlist)
            formatted.append({
                "productId": p.get("id"),
                "title": p.get("name"),
                "price": float(p.get("price")) if p.get("price") is not None else None,
                "effective_price": float(p.get("price")) if p.get("price") is not None else None,
                "discount_price": float(p.get("discount_price")) if p.get("discount_price") is not None else None,
                "description": p.get("description"),
                "category": p.get("category_name"),
                "category_id": p.get("category"),
                "images": _loads(p.get("image_urls"), []),
                "videos": _loads(p.get("videos"), []),
                "rating": float(p.get("rating")) if p.get("rating") is not None else None,
                "review_count": p.get("review_count"),
                "highlights": _loads(p.get("highlights"), []),
                "specifications": _loads(p.get("specifications"), {}),
                "whats_in_box": _loads(p.get("whats_in_box"), []),
                "stock_quantity": p.get("stock_quantity"),
                "stock_status": p.get("stock_status"),
                "computed_total_stock": computed_qty,
                "computed_stock_status": computed_status,
                "product_code": p.get("product_code"),
                "is_variable_product": bool(p.get("is_variable_product")),
                "total_sold": p.get("total_sold"),
                "created_at": p.get("created_at").isoformat() if p.get("created_at") else None,
                "updated_at": p.get("updated_at").isoformat() if p.get("updated_at") else None,
                "variations": vlist,
            })

        return formatted
    finally:
        conn.close()
