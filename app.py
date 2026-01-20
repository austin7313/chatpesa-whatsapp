import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
import pytz

# ========================
# Configuration
# ========================
PORT = int(os.environ.get("PORT", 5000))
EAT = pytz.timezone("Africa/Nairobi")

# Orders storage (in-memory for now, can be replaced by DB)
ORDERS = {}

# ========================
# Flask Setup
# ========================
app = Flask(__name__)
CORS(app)

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
    # Return all orders as a list
    orders_list = list(ORDERS.values())
    return jsonify({"status": "ok", "orders": orders_list}), 200

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

    # Generate internal receipt number
    receipt_number = f"RCP{len(ORDERS)+1:04d}"

    # Store order (initially awaiting payment)
    ORDERS[receipt_number] = {
        "id": receipt_number,
        "customer_phone": phone,
        "name": None,  # Will be filled when payment is confirmed
        "items": f"Order from WhatsApp: {message}",
        "raw_message": message,
        "amount": 0,
        "status": "awaiting_payment",
        "receipt_number": receipt_number,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Send auto-reply (simulate)
    # In real deployment, call Twilio API here
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
        bill_ref = data.get("BillRefNumber")  # matches receipt_number
        amount = float(data.get("TransAmount", 0))
        phone = data.get("MSISDN")
        first_name = data.get("FirstName", "")
        middle_name = data.get("MiddleName", "")
        last_name = data.get("LastName", "")

        full_name = " ".join([first_name, middle_name, last_name]).strip() or None

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

        # Optionally send WhatsApp confirmation (simulate)
        print(f"Payment confirmed for {bill_ref}. Name: {full_name}, Amount: {amount}")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ========================
# Run Server
# ========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
