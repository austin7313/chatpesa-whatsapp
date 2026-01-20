from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory orders storage
orders = []

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"orders": orders, "status": "ok"}), 200

@app.route("/orders", methods=["POST"])
def create_order():
    data = request.json or {}
    order_id = f"RCP{len(orders)+1:04d}"
    now = datetime.utcnow().isoformat()
    order = {
        "id": order_id,
        "customer_phone": data.get("customer_phone", "unknown"),
        "name": data.get("name", "—"),
        "items": data.get("items", "—"),
        "raw_message": data.get("raw_message", ""),
        "amount": data.get("amount", 0),
        "receipt_number": order_id,
        "status": "awaiting_payment",
        "created_at": now
    }
    orders.append(order)
    return jsonify(order), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
