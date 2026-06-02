"""
Abid Shoes - Web API
Render.com pe deploy hoga (FREE)
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3, os, datetime, json

app = Flask(__name__)
CORS(app)

DB = "abidshoes_web.db"
API_KEY = os.environ.get("API_KEY", "abidshoes2024secret")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE,
            name TEXT, brand TEXT, category TEXT,
            price REAL, stock INTEGER DEFAULT 0,
            image_url TEXT, sizes TEXT, gender TEXT DEFAULT 'Unisex', description TEXT,
            is_active INTEGER DEFAULT 1,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE,
            customer_name TEXT, customer_phone TEXT,
            customer_address TEXT, city TEXT,
            items TEXT, subtotal REAL, delivery REAL DEFAULT 200,
            total REAL, payment_method TEXT,
            status TEXT DEFAULT 'Pending',
            notes TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS shop_info(
            key TEXT PRIMARY KEY, value TEXT
        );
    """)
    # Add image_url and sizes columns if missing (for existing DBs)
    try:
        c.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
    except: pass
    try:
        c.execute("ALTER TABLE products ADD COLUMN sizes TEXT")
    except: pass
    try:
        c.execute("ALTER TABLE products ADD COLUMN gender TEXT DEFAULT 'Unisex'")
    except: pass
    
    defaults = [
        ("shop_name", "Abid Shoes"),
        ("shop_address", "Main Bazar Jhumra Road, Khurrianwala, Faisalabad"),
        ("shop_phone", "0323-866-6676"),
        ("jazzcash_no", "0323-866-6676"),
        ("easypaisa_no", "0323-866-6676"),
        ("delivery_charges", "200"),
        ("free_delivery_above", "3000"),
        ("banner_text", "Quality Footwear at Best Prices!"),
        ("banner_size", "Medium"),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO shop_info(key,value) VALUES (?,?)", (k,v))
    conn.commit(); conn.close()

init_db()

def check_key():
    key = request.headers.get("X-API-Key") or request.args.get("key")
    return key == API_KEY

@app.route("/")
def home():
    return jsonify({"status": "Abid Shoes API running", "version": "2.0"})

@app.route("/api/products")
def get_products():
    conn = get_db(); c = conn.cursor()
    brand = request.args.get("brand", "")
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    q = "SELECT * FROM products WHERE is_active=1"
    p = []
    if brand: q += " AND brand=?"; p.append(brand)
    if category: q += " AND category=?"; p.append(category)
    if search: q += " AND (name LIKE ? OR brand LIKE ?)"; p.extend(['%'+search+'%']*2)
    q += " ORDER BY brand, name"
    rows = c.execute(q, p).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/products/<int:pid>")
def get_product(pid):
    conn = get_db()
    r = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    return jsonify(dict(r)) if r else (jsonify({"error": "Not found"}), 404)

@app.route("/api/brands")
def get_brands():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT brand FROM products WHERE is_active=1 AND brand!='' ORDER BY brand").fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])

@app.route("/api/categories")
def get_categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE is_active=1 AND category!='' ORDER BY category").fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])

@app.route("/api/shop")
def get_shop():
    conn = get_db()
    rows = conn.execute("SELECT key,value FROM shop_info").fetchall()
    conn.close()
    return jsonify({r[0]: r[1] for r in rows})

@app.route("/api/orders", methods=["POST"])
def place_order():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    required = ["customer_name", "customer_phone", "customer_address", "items"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"{f} required"}), 400

    conn = get_db(); c = conn.cursor()
    now = datetime.datetime.now()
    order_no = f"WEB-{now.strftime('%Y%m%d%H%M%S')}"
    items = json.dumps(data.get("items", []))
    subtotal = float(data.get("subtotal", 0))

    free_above = float(c.execute("SELECT value FROM shop_info WHERE key='free_delivery_above'").fetchone()[0] or 3000)
    delivery_charges = float(c.execute("SELECT value FROM shop_info WHERE key='delivery_charges'").fetchone()[0] or 200)
    delivery = 0 if subtotal >= free_above else delivery_charges
    total = subtotal + delivery

    c.execute("""INSERT INTO orders(order_no,customer_name,customer_phone,
                 customer_address,city,items,subtotal,delivery,total,
                 payment_method,status,notes,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (order_no, data["customer_name"], data["customer_phone"],
               data["customer_address"], data.get("city",""),
               items, subtotal, delivery, total,
               data.get("payment_method", "COD"), "Pending",
               data.get("notes",""), now.strftime("%Y-%m-%d %H:%M")))
    conn.commit(); conn.close()

    return jsonify({
        "success": True,
        "order_no": order_no,
        "total": total,
        "delivery": delivery,
        "message": f"Order {order_no} placed successfully!"
    })

@app.route("/api/orders/<order_no>")
def track_order(order_no):
    conn = get_db()
    r = conn.execute("SELECT order_no,customer_name,status,total,created_at FROM orders WHERE order_no=?", (order_no,)).fetchone()
    conn.close()
    if not r: return jsonify({"error": "Order not found"}), 404
    return jsonify(dict(r))

# ── POS ENDPOINTS ──

@app.route("/api/sync", methods=["POST"])
def sync_from_pos():
    if not check_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    if not data or "products" not in data:
        return jsonify({"error": "No products data"}), 400

    conn = get_db(); c = conn.cursor()
    updated = 0
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for p in data["products"]:
        # ✅ image_url aur sizes bhi save ho raha hai
        c.execute("""INSERT OR REPLACE INTO products
                     (barcode,name,brand,category,price,stock,image_url,sizes,gender,is_active,updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
                  (p.get("barcode",""), p.get("name",""),
                   p.get("brand",""), p.get("category",""),
                   float(p.get("price",0)), int(p.get("stock",0)),
                   p.get("image_url",""), p.get("sizes",""),
                   p.get("gender","Unisex"), now))
        updated += 1
    
    # Shop info bhi update
    if "shop_info" in data:
        for k, v in data["shop_info"].items():
            c.execute("INSERT OR REPLACE INTO shop_info(key,value) VALUES (?,?)", (k,v))
    
    conn.commit(); conn.close()
    return jsonify({"success": True, "updated": updated, "time": now})

@app.route("/api/orders/list")
def list_orders():
    if not check_key():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    status = request.args.get("status", "")
    q = "SELECT * FROM orders"
    if status: q += f" WHERE status='{status}'"
    q += " ORDER BY id DESC LIMIT 100"
    rows = conn.execute(q).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/orders/<order_no>/status", methods=["PUT"])
def update_order_status(order_no):
    if not check_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    conn = get_db()
    conn.execute("UPDATE orders SET status=? WHERE order_no=?",
                 (data.get("status","Pending"), order_no))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/api/shop/update", methods=["POST"])
def update_shop():
    if not check_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    conn = get_db(); c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO shop_info(key,value) VALUES (?,?)", (k,v))
    conn.commit(); conn.close()
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
