import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime, timezone
import pytz

# ========================
# Config
# ========================
PORT = int(os.environ.get("PORT", 5000))
EAT = pytz.timezone("Africa/Nairobi")

ORDERS = {}

# ========================
# Flask Setup
# ========================
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")  # WebSocket server

# ========================
# Health Check
# ========================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ========================
# Orders Endpoint
# ========================
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": list(ORDERS.values())}), 200

# ========================
# WhatsApp Webhook
# ========================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.json
    phone = data.get("from")
    message = data.get("message", "").strip()

    if not phone or not message:
        return jsonify({"status": "error", "message": "Missing phone or message"}), 400

    receipt_number = f"RCP{len(ORDERS)+1:04d}"
    order = {
        "id": receipt_number,
        "customer_phone": phone,
        "name": None,
        "items": f"Order from WhatsApp: {message}",
        "raw_message": message,
        "amount": 0,
        "status": "awaiting_payment",
        "receipt_number": receipt_number,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    ORDERS[receipt_number] = order

    # Notify dashboard instantly
    socketio.emit("new_order", order, broadcast=True)

    # Simulated auto-reply
    reply = f"Thanks! Your order {receipt_number} is received. Awaiting payment."
    print(f"Auto-reply to {phone}: {reply}")

    return jsonify({"status": "ok", "receipt_number": receipt_number, "reply": reply}), 200

# ========================
# M-Pesa Payment Webhook
# ========================
@app.route("/webhook/mpesa", methods=["POST"])
def mpesa_webhook():
    data = request.json
    try:
        bill_ref = data.get("BillRefNumber")
        amount = float(data.get("TransAmount", 0))
        phone = data.get("MSISDN")
        full_name = " ".join(filter(None, [data.get("FirstName"), data.get("MiddleName"), data.get("LastName")])) or None

        if bill_ref not in ORDERS:
            return jsonify({"status": "error", "message": "Unknown order"}), 404

        # Update order
        ORDERS[bill_ref].update({
            "amount": amount,
            "name": full_name,
            "status": "paid",
            "payment_phone": phone,
            "paid_at": datetime.now(timezone.utc).isoformat()
        })

        # Notify dashboard instantly
        socketio.emit("payment_update", ORDERS[bill_ref], broadcast=True)
        print(f"Payment confirmed for {bill_ref}. Name: {full_name}, Amount: {amount}")

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ========================
# Run Server
# ========================
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT)
