from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import psycopg2
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)  # ✅ ALLOWS VERCEL DASHBOARD TO ACCESS API

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, customer_name, phone, amount, status, created_at, receipt, service
            FROM orders
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        orders = []
        for r in rows:
            orders.append({
                "id": r[0],
                "name": r[1],
                "phone": r[2],
                "amount": r[3],
                "status": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "receipt": r[6] or None,
                "service": r[7] or None
            })

        return jsonify(orders), 200
    except Exception as e:
        print("❌ /orders error:", e)
        return jsonify([]), 200

# WhatsApp webhook remains unchanged
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        from_number = request.form.get("From")
        body = request.form.get("Body", "").strip()
        if not from_number or not body:
            return "OK", 200

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (customer_name, phone, amount, status, created_at, service)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "WhatsApp User",
            from_number,
            "10",
            "PENDING",
            datetime.now(timezone.utc),
            body
        ))
        conn.commit()
        cur.close()
        conn.close()
        return "OK", 200
    except Exception as e:
        print("❌ WhatsApp webhook error:", e)
        return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("🚀 ChatPesa backend running on port", port)
    app.run(host="0.0.0.0", port=port)
