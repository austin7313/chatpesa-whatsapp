from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)  # ✅ Allow React frontend to fetch

# In-memory orders store (replace with DB later)
ORDERS = []

# Health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# Orders endpoint
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "orders": ORDERS,
        "status": "ok"
    }), 200

# Twilio webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    from_number = request.values.get("From", "")
    body = request.values.get("Body", "")
    
    # Generate a simple order ID
    order_id = f"ORD{len(ORDERS)+1:03d}"
    
    # Capture timestamp in EAT (UTC+3)
    eat = pytz.timezone("Africa/Nairobi")
    now_eat = datetime.now(eat).isoformat()
    
    # Fake order creation
    order = {
        "id": order_id,
        "customer_phone": from_number,
        "items": body,
        "amount": 10,  # replace with dynamic logic later
        "status": "paid",
        "receipt_number": f"RCP{len(ORDERS)+1:03d}",
        "created_at": now_eat
    }
    
    ORDERS.append(order)
    
    # Log for debugging
    print(f"Received WhatsApp message from {from_number}: {body}")
    print(f"Order stored: {order}")
    
    # Respond to Twilio immediately with empty TwiML
    twiml_response = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return twiml_response, 200, {'Content-Type': 'application/xml'}

# Run server
if __name__ == "__main__":
    app.run(debug=True)
