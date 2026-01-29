from flask import Flask, request, jsonify, Response
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)

# ===============================
# DATABASE CONNECTION
# ===============================
DATABASE_URL = os.environ.get("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True

print("🔹 ✅ Database connected")

# ===============================
# HEALTH CHECK
# ===============================
@app.route("/")
def home():
    return "ChatPesa backend running"

# ===============================
# WHATSAPP WEBHOOK
# ===============================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        from_number = request.form.get("From", "")
        body = request.form.get("Body", "").strip()

        if not body:
            return Response(
                "<Response><Message>Please send a service or order.</Message></Response>",
                mimetype="application/xml"
            )

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (customer_name, phone, amount, status, service, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "WhatsApp User",
            from_number,
            10,
            "PENDING",
            body,
            datetime.utcnow()
        ))
        cur.close()

        reply = f"""
<Response>
  <Message>
✅ Order received

Service: {body}
Amount: KES 10
Status: PENDING
  </Message>
</Response>
        """

        return Response(reply, mimetype="application/xml")

    except Exception as e:
        print("❌ WhatsApp Error:", e)
        return Response(
            "<Response><Message>System error. Try again.</Message></Response>",
            mimetype="application/xml"
        )

# ===============================
# DASHBOARD ORDERS API
# ===============================
@app.route("/orders", methods=["GET"])
def get_orders():
    cur = conn.cursor()
    cur.execute("""
        SELECT id, customer_name, phone, amount, status, service, created_at
        FROM orders
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()

    orders = []
    for r in rows:
        orders.append({
            "id": r[0],
            "name": r[1],
            "phone": r[2],
            "amount": r[3],
            "status": r[4],
            "service": r[5],
            "created_at": r[6].isoformat()
        })

    return jsonify(orders)

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
