from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# In-memory storage for simplicity
ORDERS = []

# Health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# Get orders
@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": ORDERS})

# Receive WhatsApp / M-Pesa messages
@app.route("/new_order", methods=["POST"])
def new_order():
    data = request.json
    # Extract fields safely
    customer_phone = data.get("customer_phone")
    raw_message = data.get("raw_message")
    receipt_number = data.get("receipt_number")
    amount = data.get("amount", 0)
    name = data.get("name") or "—"  # This can later be fetched from M-Pesa callback

    order_id = f"RCP{len(ORDERS)+1:04d}"
    created_at = datetime.now(pytz.timezone("Africa/Nairobi")).isoformat()

    order = {
        "id": order_id,
        "customer_phone": customer_phone,
        "name": name,
        "items": raw_message,
        "amount": amount,
        "status": "awaiting_payment",
        "receipt_number": receipt_number,
        "created_at": created_at
    }
    ORDERS.append(order)

    # Emit to dashboard in real-time
    socketio.emit("new_order", order)

    return jsonify({"status": "ok", "order": order})

# Update order payment (from M-Pesa callback)
@app.route("/update_payment", methods=["POST"])
def update_payment():
    receipt_number = request.json.get("receipt_number")
    mpesa_name = request.json.get("name")  # Payer name from M-Pesa
    amount = request.json.get("amount", 0)

    for order in ORDERS:
        if order["receipt_number"] == receipt_number:
            order["status"] = "paid"
            order["name"] = mpesa_name
            order["amount"] = amount
            socketio.emit("update_order", order)
            return jsonify({"status": "ok", "order": order})

    return jsonify({"status": "not_found"}), 404

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
