from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime, timezone, timedelta
import uuid

app = Flask(__name__)
CORS(app)  # Enable CORS for dashboard

# In-memory "database" (for demo purposes)
orders_db = []

# Helper to get East Africa Time
def now_eat():
    return datetime.now(timezone.utc) + timedelta(hours=3)

# Health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# Get all orders
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "orders": orders_db,
        "status": "ok"
    })

# Create order helper
def create_order(customer_phone, amount):
    order_id = f"ORD{len(orders_db)+1:04d}"
    timestamp = now_eat().isoformat()
    order = {
        "id": order_id,
        "customer_phone": customer_phone,
        "amount": amount,
        "status": "paid",
        "receipt_number": f"RCP{len(orders_db)+1:04d}",
        "created_at": timestamp
    }
    return order

# Twilio webhook for WhatsApp messages
@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "").strip()
    
    resp = MessagingResponse()
    
    # Simple demo: if message is a number, create order
    if incoming_msg.isdigit():
        amount = int(incoming_msg)
        order = create_order(customer_phone=from_number, amount=amount)
        orders_db.append(order)
        resp.message(f"✅ Order received! Amount: KES {amount}, Order ID: {order['id']}")
    else:
        resp.message("Welcome to ChatPesa! Send an amount in KES to place an order.")
    
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
