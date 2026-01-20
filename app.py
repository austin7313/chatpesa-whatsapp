from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
import pytz
from datetime import datetime

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# In-memory orders storage (replace with DB for production)
orders = []

# API: health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# API: get all orders
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": orders}), 200

# API: create new order (from WhatsApp/M-Pesa)
@app.route("/orders", methods=["POST"])
def create_order():
    data = request.json
    order_id = f"RCP{len(orders)+1:04d}"

    # Extract MPESA name if exists
    customer_name = data.get("mpesa_name") or data.get("name") or "—"

    order = {
        "order_id": order_id,
        "customer_phone": data.get("phone", "—"),
        "name": customer_name,
        "items": data.get("items", "—"),
        "amount": data.get("amount", "—"),
        "status": data.get("status", "AWAITING_PAYMENT"),
        "receipt": order_id,
        "created_at": datetime.now(pytz.timezone("Africa/Nairobi")).strftime("%d/%m/%Y, %H:%M")
    }

    orders.append(order)

    # Notify dashboard via WebSocket
    socketio.emit("new_order", order)
    return jsonify({"status": "ok", "order": order}), 201

# Run app
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
