from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory store (safe for now)
orders = []

# ===============================
# HEALTH CHECK
# ===============================
@app.route("/health")
def health():
    return {"status": "ok"}

# ===============================
# DASHBOARD ORDERS API
# ===============================
@app.route("/orders")
def get_orders():
    return {
        "status": "ok",
        "orders": orders
    }

# ===============================
# WHATSAPP WEBHOOK (CRITICAL)
# ===============================
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    try:
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        body = request.form.get("Body", "").strip()

        order_id = f"RCP{len(orders) + 1001}"
        amount = 1000  # static for now

        order = {
            "id": order_id,
            "customer_phone": from_number,
            "customer_name": from_number,  # replaced after M-Pesa
            "items": body if body else "Custom Order",
            "amount": amount,
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.now().isoformat(),
            "paid_at": None,
            "mpesa_name": None,
            "mpesa_receipt": None
        }

        orders.insert(0, order)

        resp = MessagingResponse()
        resp.message(
            f"Order received.\n\n"
            f"Order ID: {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Pay via M-Pesa:\n"
            f"Reference: {order_id}\n\n"
            f"Reply DONE after payment."
        )

        return str(resp), 200, {"Content-Type": "text/xml"}

    except Exception as e:
        resp = MessagingResponse()
        resp.message("Sorry, something went wrong. Please try again.")
        return str(resp), 200, {"Content-Type": "text/xml"}

# ===============================
# MPESA CALLBACK (READY)
# ===============================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json

    try:
        callback = data["Body"]["stkCallback"]
        if callback["ResultCode"] != 0:
            return jsonify({"status": "failed"})

        meta = callback["CallbackMetadata"]["Item"]

        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
        phone = next(i["Value"] for i in meta if i["Name"] == "PhoneNumber")
        name = next(i["Value"] for i in meta if i["Name"] == "PayerName")

        # Match latest unpaid order by phone
        for order in orders:
            if order["customer_phone"].endswith(str(phone)[-9:]) and order["status"] == "AWAITING_PAYMENT":
                order["status"] = "PAID"
                order["mpesa_name"] = name
                order["customer_name"] = name
                order["mpesa_receipt"] = receipt
                order["paid_at"] = datetime.now().isoformat()
                break

        return jsonify({"status": "ok"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
