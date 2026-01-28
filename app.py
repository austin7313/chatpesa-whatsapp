import os
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from twilio.rest import Client
from datetime import datetime

# ===========================
# ENV VARIABLES
# ===========================
DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")

if not all([DATABASE_URL, TWILIO_SID, TWILIO_AUTH, TWILIO_WHATSAPP_NUMBER]):
    raise RuntimeError("❌ One or more environment variables are not set!")

# ===========================
# FLASK APP
# ===========================
app = Flask(__name__)

# ===========================
# DATABASE CONNECTION
# ===========================
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

# ===========================
# INITIALIZE TABLE
# ===========================
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_id TEXT UNIQUE,
            customer_name TEXT,
            phone TEXT,
            amount TEXT,
            status TEXT,
            service TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("🔹 ✅ Database initialized")

# ===========================
# TWILIO CLIENT
# ===========================
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

def send_whatsapp(to, body):
    """Send WhatsApp message via Twilio"""
    message = twilio_client.messages.create(
        body=body,
        from_="whatsapp:" + TWILIO_WHATSAPP_NUMBER,
        to=to
    )
    return message.sid

# ===========================
# WHATSAPP WEBHOOK
# ===========================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        data = request.form
        from_number = data.get("From")       # e.g., "whatsapp:+2547..."
        body = data.get("Body") or "No message"

        # Normalize phone
        if from_number.startswith("whatsapp:"):
            from_number = from_number.replace("whatsapp:", "")

        # Generate order_id
        order_id = f"CP{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Insert into DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (order_id, customer_name, phone, amount, status, service)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (order_id, "WhatsApp User", from_number, "10", "PENDING", body))
        conn.commit()
        cur.close()
        conn.close()

        # Reply to user
        send_whatsapp("whatsapp:" + from_number, f"✅ Your order {order_id} is received! We will notify you once payment is confirmed.")

        return jsonify({"status": "ok", "order_id": order_id})
    except Exception as e:
        print("❌ Error in WhatsApp webhook:", e)
        return "Internal Server Error", 500

# ===========================
# GET ORDERS (Dashboard API)
# ===========================
@app.route("/orders", methods=["GET"])
def get_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC;")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "orders": orders})

# ===========================
# MAIN
# ===========================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    print(f"🔹 🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
