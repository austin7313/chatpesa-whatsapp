from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory store (later we swap to DB)
orders = []

# --------------------
# HEALTH CHECK
# --------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# --------------------
# DASHBOARD ORDERS
# --------------------
@app.route("/orders")
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": orders
    })

# --------------------
# CREATE ORDER (WhatsApp)
# --------------------
@app.route("/create-order", methods=["POST"])
def create_order():
    data = request.json

    order = {
        "id": data["order_id"],
        "customer_phone": data["phone"],
        "customer_name": data.get("whatsapp_name", data["phone"]),
        "items": data["items"],
        "amount": data["amount"],
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.now().isoformat(),
        "paid_at": None,
        "mpesa_name": None,
        "mpesa_receipt": None
    }

    orders.insert(0, order)
    return jsonify({"status": "ok"})

# --------------------
# M-PESA CALLBACK
# --------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json

    receipt = data["MpesaReceiptNumber"]
    phone = data["PhoneNumber"]
    name = data["CustomerName"]
    amount = data["Amount"]

    for order in orders:
        if (
            order["customer_phone"] == phone
            and order["amount"] == amount
            and order["status"] == "AWAITING_PAYMENT"
        ):
            order["status"] = "PAID"
            order["mpesa_receipt"] = receipt
            order["mpesa_name"] = name
            order["customer_name"] = name  # 🔥 REPLACE WHATSAPP NAME
            order["paid_at"] = datetime.now().isoformat()
            break

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

# --------------------
# LOCAL TEST ORDER
# --------------------
@app.route("/test-order")
def test_order():
    orders.insert(0, {
        "id": "TEST001",
        "customer_phone": "254700000000",
        "customer_name": "Test User",
        "items": "Demo",
        "amount": 100,
        "status": "PAID",
        "created_at": datetime.now().isoformat(),
        "paid_at": datetime.now().isoformat(),
        "mpesa_name": "Test User",
        "mpesa_receipt": "ABC123"
    })
    return {"added": True}

if __name__ == "__main__":
    app.run()
