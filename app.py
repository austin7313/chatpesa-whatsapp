from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime
import pytz
from twilio.twiml.messaging_response import MessagingResponse  # ✅ Official Twilio library

app = Flask(__name__)
CORS(app)

# In-memory orders (replace with DB in production)
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

# Twilio webhook for WhatsApp
@app.route("/webhook", methods=["POST"])
def webhook():
    from_number = request.values.get("From", "")
    body = request.values.get("Body", "")
    
    # Auto-generate order ID
    order_id = f"ORD{len(ORDERS)+1:03d}"
    
    # Timestamp in EAT
    eat = pytz.timezone("Africa/Nairobi")
    now_eat = datetime.now(eat).isoformat()
    
    # Fake order creation
    order = {
        "id": order_id,
        "customer_phone": from_number,
        "items": body,
        "amount": 10,  # You can calculate dynamically later
        "status": "paid",
        "receipt_number": f"RCP{len(ORDERS)+1:03d}",
        "created_at": now_eat
    }
    ORDERS.append(order)
    
    print(f"Received message from {from_number}: {body}")
    print(f"Order stored: {order}")
    
    # Proper TwiML response
    resp = MessagingResponse()
    resp.message("✅ Your order has been received!")
    return Response(str(resp), mimetype="application/xml")  # ✅ Correct TwiML response

if __name__ == "__main__":
    app.run(debug=True)
