from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import uuid
import datetime
import os

app = Flask(__name__)
CORS(app)

ORDERS = {}  # replace with DB later

def now():
    return datetime.datetime.now().isoformat()

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    msg = request.form.get("Body", "").strip().upper()
    sender = request.form.get("From")

    resp = MessagingResponse()
    reply = resp.message()

    # PAY confirmation
    if msg == "PAY":
        pending = [o for o in ORDERS.values() if o["phone"] == sender and o["status"] == "AWAITING_PAYMENT"]
        if not pending:
            reply.body("No pending order found.")
            return str(resp)

        order = pending[-1]
        # 🔔 STK PUSH WILL BE TRIGGERED HERE (next phase)
        reply.body("M-Pesa payment request sent 📲\nEnter your PIN to complete payment.")
        return str(resp)

    # Create new order
    order_id = f"CP{uuid.uuid4().hex[:6].upper()}"
    ORDERS[order_id] = {
        "id": order_id,
        "name": sender,
        "phone": sender,
        "items": msg or "Custom Order",
        "amount": 1000,
        "status": "AWAITING_PAYMENT",
        "created_at": now()
    }

    reply.body(
        f"Order created ✅\n"
        f"Order ID: {order_id}\n"
        f"Amount: KES 1000\n\n"
        f"Reply PAY to pay via M-Pesa"
    )
    return str(resp)

@app.route("/orders")
def orders():
    return jsonify({
        "status": "ok",
        "orders": list(ORDERS.values())
    })

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run()
