from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import uuid
import os

app = Flask(__name__)
CORS(app)

# -----------------------------
# In-memory store (safe for now)
# -----------------------------
ORDERS = []

# -----------------------------
# Universal Twilio Webhook
# -----------------------------
@app.route("/", methods=["POST", "GET"])
@app.route("/whatsapp", methods=["POST", "GET"])
@app.route("/webhook/whatsapp", methods=["POST", "GET"])
@app.route("/twilio", methods=["POST", "GET"])
@app.route("/twilio/whatsapp", methods=["POST", "GET"])
def twilio_webhook():
    """
    ONE webhook to rule them all.
    Accepts any Twilio WhatsApp/SMS webhook path.
    Always responds with valid TwiML.
    """

    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    timestamp = datetime.utcnow().isoformat()

    print("📩 TWILIO MESSAGE")
    print("From:", from_number)
    print("Body:", incoming_msg)

    # Generate Order
    order_id = f"CP{uuid.uuid4().hex[:6].upper()}"

    order = {
        "id": order_id,
        "customer_name": from_number,  # replaced later by M-Pesa name
        "customer_phone": from_number,
        "items": incoming_msg or "Custom Order",
        "amount": 1000,
        "status": "AWAITING_PAYMENT",
        "created_at": timestamp,
    }

    ORDERS.insert(0, order)

    resp = MessagingResponse()
    resp.message(
        f"✅ ChatPesa Order Created\n\n"
        f"Order ID: {order_id}\n"
        f"Amount: KES 1000\n\n"
        f"You will receive an M-Pesa prompt shortly."
    )

    return str(resp), 200, {"Content-Type": "text/xml"}

# -----------------------------
# Dashboard API
# -----------------------------
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": ORDERS
    })

# -----------------------------
# Health Check (Render / Uptime)
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ChatPesa"}), 200

# -----------------------------
# App Entrypoint
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
