from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
import uuid

app = Flask(__name__)
CORS(app)

# In-memory "database" for orders (replace with real DB later)
orders = []

# East Africa Timezone
EAT = pytz.timezone("Africa/Nairobi")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"orders": orders, "status": "ok"}), 200

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        data = request.json
        phone = data.get("from") or data.get("customer_phone") or "unknown"
        amount = float(data.get("amount", 0))
        items = data.get("items") or data.get("message") or "—"
        status = data.get("status", "paid").lower()
        
        # Generate Order ID
        order_id = len(orders) + 1
        
        # Generate Receipt Number
        receipt_number = f"RCP{str(order_id).zfill(4)}"
        
        # Timestamp in East Africa Time
        now_eat = datetime.now(EAT).isoformat()
        
        # Create order
        order = {
            "id": order_id,
            "customer_phone": phone,
            "amount": amount,
            "items": items,
            "status": status,
            "receipt_number": receipt_number,
            "created_at": now_eat
        }
        
        orders.append(order)
        
        # Respond with success
        return jsonify({
            "status": "ok",
            "order": order
        }), 200
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # Use port from Render environment
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
