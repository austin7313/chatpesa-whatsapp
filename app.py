import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory storage (replace with DB for production)
orders = []

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "ChatPesa API ONLINE"}), 200

@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": orders}), 200

@app.route("/webhook/mpesa", methods=["POST"])
def mpesa_webhook():
    data = request.json
    # Example M-Pesa callback structure
    order_id = data.get("OrderID")
    customer_name = data.get("CustomerName")
    customer_phone = data.get("CustomerPhone")
    items = data.get("Items")
    amount = data.get("Amount")
    status = data.get("Status")  # PAID / FAILED / AWAITING_PAYMENT

    # Check if order exists
    existing = next((o for o in orders if o["id"] == order_id), None)
    if existing:
        existing.update({
            "status": status,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "updated_at": datetime.now().isoformat()
        })
    else:
        orders.append({
            "id": order_id,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "items": items,
            "amount": amount,
            "status": status,
            "created_at": datetime.now().isoformat()
        })
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
