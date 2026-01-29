from flask import Flask, request, jsonify, Response
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True

print("✅ Database connected")

# ===============================
# AUTO-FIX DATABASE (CRITICAL)
# ===============================
def init_db():
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer_name TEXT,
            phone TEXT,
            amount INTEGER,
            status TEXT,
            created_at TIMESTAMP
        );
    """)
    cur.close()
    print("✅ Database schema ensured")

init_db()

# ===============================
# HEALTH CHECK
# ===============================
@app.route("/")
def home():
    return "ChatPesa backend running"

# ===============================
# WHATSAPP WEBHOOK (BULLETPROOF)
# ===============================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    from_number = request.form.get("From", "")
    body = request.form.get("Body", "").strip()

    if not body:
        body = "Unknown item"

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (customer_name, phone, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            body,
            from_number,
            10,
            "PENDING",
            datetime.utcnow()
        ))
        cur.close()

        reply = f"""
<Response>
  <Message>
✅ Order received

Item: {body}
Amount: KES 10
Status: PENDING
  </Message>
</Response>
        """

        return Response(reply, mimetype="application/xml")

    except Exception as e:
        print("❌ WHATSAPP INSERT ERROR:", e)

        return Response("""
<Response>
  <Message>
⚠️ System busy. Please resend your message.
  </Message>
</Response>
        """, mimetype="application/xml")

# ===============================
# DASHBOARD API
# ===============================
@app.route("/orders", methods=["GET"])
def get_orders():
    cur = conn.cursor()
    cur.execute("""
        SELECT id, customer_name, phone, amount, status, created_at
        FROM orders
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()

    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "phone": r[2],
            "amount": r[3],
            "status": r[4],
            "created_at": r[5].isoformat()
        } for r in rows
    ])

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
