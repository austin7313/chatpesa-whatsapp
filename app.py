# app.py — Full Replacement for ChatPesa Dashboard

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import uuid

app = Flask(__name__)
CORS(app)

# In-memory orders database (replace with real DB later)
orders_db = []

# Utility: generate a new order
def create_order(customer_phone, amount, status="paid", receipt_number=None, items=None):
    order_id = str(uuid.uuid4())[:8]  # short unique ID
    timestamp = datetime.utcnow().isoformat()  # UTC timestamp
    return {
        "id": order_id,
        "customer_phone": customer_phone,
        "amount": amount,
        "status": status,
        "receipt_number": receipt_number or f"RCP{len(orders_db)+1:04d}",
        "items": items or "Item description",
        "created_at": timestamp
    }

# Health endpoint
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# Orders endpoint
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"orders": orders_db, "status": "ok"})

# Create order endpoint (for testing or webhook)
@app.route("/create_order", methods=["POST"])
def add_order():
    data = request.get_json()
    if not data or "customer_phone" not in data or "amount" not in data:
        return jsonify({"error": "Missing customer_phone or amount"}), 400
    
    order = create_order(
        customer_phone=data["customer_phone"],
        amount=data["amount"],
        status=data.get("status", "paid"),
        receipt_number=data.get("receipt_number"),
        items=data.get("items")
    )
    orders_db.append(order)
    return jsonify({"message": "Order created", "order": order}), 201

# Optional: reset orders (testing)
@app.route("/reset_orders", methods=["POST"])
def reset_orders():
    orders_db.clear()
    return jsonify({"message": "Orders cleared"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
