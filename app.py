from flask import Flask, request, jsonify, Response
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True

print("✅ Database connected")

@app.route("/")
def home():
    return "ChatPesa backend running"

# ===============================
# WHATSAPP WEBHOOK (FIXED)
# ===============================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        from_number = request.form.get("From", "")
        body = request.form.get("Body", "").strip()

        if not body:
            body = "Unknown service"

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (customer_name, phone, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            body,               # store service text here for now
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
        print("❌ WHATSAPP ERROR:", e)
        return Response(
            "<Response><Message>Temporary error. Please retry.</Message></Response>",
            mimetype="application/xml"
        )

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

    orders = []
    for r in rows:
        orders.append({
            "id": r[0],
            "name": r[1],
            "phone": r[2],
            "amount": r[3],
            "status": r[4],
            "created_at": r[5].isoformat()
        })

    return jsonify(orders)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
