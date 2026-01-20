from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone, timedelta

app = Flask(__name__)
CORS(app)  # Allow dashboard requests

# In-memory orders list (replace with your DB if needed)
orders_list = []

# Example order structure
# {
#   "id": "RCP0001",
#   "customer_phone": "whatsapp:+254722275271",
#   "name": "Bryce",
#   "items": "Order from WhatsApp: Order 1",
#   "amount": 0,
#   "status": "awaiting_payment",
#   "receipt_number": "RCP0001",
#   "created_at": datetime.utcnow().isoformat()
# }

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/orders", methods=["GET"])
def get_orders():
    # Return orders sorted by created_at descending
    sorted_orders = sorted(
        orders_list, 
        key=lambda o: o.get("created_at", ""), 
        reverse=True
    )
    return jsonify({"orders": sorted_orders, "status": "ok"}), 200

@app.route("/orders", methods=["POST"])
def add_order():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    order = {
        "id": data.get("id") or f"RCP{len(orders_list)+1:04}",
        "customer_phone": data.get("customer_phone"),
        "name": data.get("name", "—"),  # Default to — if name missing
        "items": data.get("items"),
        "amount": data.get("amount", 0),
        "status": data.get("status", "awaiting_payment"),
        "receipt_number": data.get("receipt_number") or f"RCP{len(orders_list)+1:04}",
        "created_at": datetime.utcnow().isoformat()
    }
    orders_list.append(order)
    return jsonify({"order": order, "status": "ok"}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
