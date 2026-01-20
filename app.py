from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import pytz
from datetime import datetime
import json
import os

app = Flask(__name__)
CORS(app)

# Persistent JSON storage
ORDERS_FILE = "orders.json"
if os.path.exists(ORDERS_FILE):
    with open(ORDERS_FILE, "r") as f:
        orders = json.load(f)
else:
    orders = []

# Helper to save orders
def save_orders():
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": orders})

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.form if request.form else request.json
    from_number = data.get("From")
    body = data.get("Body", "").strip()

    # Parse name if user sends "Name: <name>"
    if body.lower().startswith("name:"):
        name = body[5:].strip()
        reply_msg = f"Thanks {name}! You can now send your order."
        resp = MessagingResponse()
        resp.message(reply_msg)
        return str(resp)

    # Otherwise, treat as an order
    order_id = f"RCP{len(orders)+1:04d}"
    name = None
    # Check if user already has a name stored
    for o in orders:
        if o["customer_phone"] == from_number and o.get("name"):
            name = o["name"]
            break

    order = {
        "id": order_id,
        "customer_phone": from_number,
        "name": name,
        "raw_message": body,
        "items": f"Order from WhatsApp: {body}",
        "amount": 0,
        "status": "awaiting_payment",
        "receipt_number": order_id,
        "created_at": datetime.utcnow().replace(tzinfo=pytz.UTC).isoformat()
    }
    orders.append(order)
    save_orders()

    # Reply back
    reply_text = f"Received your order! Receipt: {order_id}"
    if name:
        reply_text = f"Hi {name}, {reply_text}"
    else:
        reply_text = f"{reply_text} (Send 'Name: YourName' to personalize.)"

    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
