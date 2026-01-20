from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
import uuid

app = Flask(__name__)
CORS(app)

# In-memory order storage (replace with DB later)
orders = []

# Helper: Format timestamp to EAT
def now_eat_iso():
    return datetime.now(pytz.timezone("Africa/Nairobi")).isoformat()

# Webhook endpoint for Twilio WhatsApp
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.form or request.json
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400

    phone = data.get("From") or data.get("from")  # Twilio sends 'From'
    body = data.get("Body") or data.get("body") or ""
    name = data.get("ProfileName") or "Unknown"       # Twilio optional field

    # Generate receipt/order ID
    receipt_number = f"RCP{str(uuid.uuid4())[:8].upper()}"

    # Save order
    order = {
        "id": receipt_number,
        "customer_phone": phone,
        "name": name,
        "items": f"Order from WhatsApp: {body}",
        "raw_message": body,
        "amount": 0,
        "status": "awaiting_payment",
        "receipt_number": receipt_number,
        "created_at": now_eat_iso()
    }
    orders.append(order)

    # Immediate Twilio reply (empty message avoids 11200 errors)
    twilio_reply = f"Hi {name}, we received your order '{body}'. Your receipt number is {receipt_number}."
    
    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{twilio_reply}</Message>
</Response>"""
    
    return response_xml, 200, {"Content-Type": "text/xml"}

# Orders endpoint for dashboard
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"orders": orders, "status": "ok"})

# Health endpoint for dashboard status
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# Optional: Reset orders (for testing)
@app.route("/reset_orders", methods=["POST"])
def reset_orders():
    global orders
    orders = []
    return jsonify({"status": "ok", "message": "Orders reset"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
