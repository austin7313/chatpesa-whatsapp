# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import requests
import datetime
import uuid

app = Flask(__name__)
CORS(app)

# In-memory storage for demo purposes; replace with DB in production
ORDERS = []

# ----------------- CONFIG -----------------
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_ENV = "sandbox"  # change to 'production' later
MPESA_STK_CALLBACK = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"
TWILIO_WHATSAPP = True  # whether to reply via WhatsApp

# ------------- HELPERS -------------------

def create_order(customer_phone, items, amount):
    """Create a new order"""
    order_id = "CP" + uuid.uuid4().hex[:6].upper()
    order = {
        "id": order_id,
        "customer_name": customer_phone,  # replace with M-Pesa name after payment
        "customer_phone": customer_phone,
        "items": items,
        "amount": amount,
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.datetime.now().isoformat()
    }
    ORDERS.append(order)
    return order

def update_order_payment(order_id, name):
    """Mark order as PAID with M-Pesa name"""
    for order in ORDERS:
        if order["id"] == order_id:
            order["status"] = "PAID"
            order["customer_name"] = name
            order["paid_at"] = datetime.datetime.now().isoformat()
            return order
    return None

def get_order_by_phone(phone):
    for order in ORDERS:
        if order["customer_phone"] == phone and order["status"] == "AWAITING_PAYMENT":
            return order
    return None

# ------------- ROUTES --------------------

@app.route("/")
def index():
    return jsonify({"status": "ok", "orders": ORDERS})

# ---------------- TWILIO WHATSAPP -------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From", "")
    resp = MessagingResponse()

    # Check if customer has pending order
    order = get_order_by_phone(from_number)

    if order:
        if incoming_msg == "pay":
            # Here you can call STK push function
            resp.message(f"STK push sent for order {order['id']}. Please complete payment on your phone.")
        else:
            resp.message(f"Hi! Reply PAY to pay for your order {order['id']} of KES {order['amount']}.")
    else:
        resp.message("Hi! No active orders found. Reply with order details to create a new order.")

    return str(resp), 200

# ----------------- CREATE ORDER ------------------
@app.route("/order", methods=["POST"])
def create_order_endpoint():
    data = request.json
    customer_phone = data.get("customer_phone")
    items = data.get("items", "Custom Order")
    amount = data.get("amount", 1000)
    order = create_order(customer_phone, items, amount)
    return jsonify({"status": "ok", "order": order})

# ----------------- M-PESA STK PUSH ----------------
@app.route("/mpesa/stkpush", methods=["POST"])
def stk_push():
    data = request.json
    phone = data.get("phone")
    amount = int(data.get("amount", 1))
    order = get_order_by_phone(phone)
    if not order:
        return jsonify({"status": "error", "message": "No pending order"}), 400

    # Normally here you call Safaricom API with the credentials
    # For demo, we just simulate STK push
    return jsonify({"status": "ok", "message": f"STK push initiated for KES {amount} to {phone}"}), 200

# ----------------- M-PESA CALLBACK ----------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    # Extract order id and customer name from callback
    order_id = data.get("order_id")
    customer_name = data.get("customer_name", "Unknown")
    update_order_payment(order_id, customer_name)
    return jsonify({"status": "ok"}), 200

# ----------------- GET ORDERS -----------------
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": ORDERS})

# ---------------- RUN APP -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
