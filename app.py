from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)

# In-memory orders store (for testing, can later connect to DB)
orders = []

# Endpoint to get all orders
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": orders
    })

# Endpoint to create new order (from WhatsApp / MPesa webhook)
@app.route("/orders", methods=["POST"])
def create_order():
    data = request.json or {}

    orderId = f"RCP{len(orders)+1:04d}"
    customerPhone = data.get("customerPhone") or "—"
    name = data.get("mpesaName") or data.get("name") or "—"
    items = data.get("items") or f"Order from WhatsApp: {orderId}"
    amount = data.get("amount") or "—"
    status = data.get("status") or "AWAITING_PAYMENT"
    receipt = orderId
    createdAt = datetime.now(pytz.timezone("Africa/Nairobi")).strftime("%d/%m/%Y, %H:%M")

    order = {
        "orderId": orderId,
        "customerPhone": customerPhone,
        "mpesaName": data.get("mpesaName"),
        "name": name,
        "items": items,
        "amount": amount,
        "status": status,
        "receipt": receipt,
        "createdAt": createdAt
    }

    orders.append(order)
    return jsonify({"status": "ok", "order": order}), 201

# Health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
