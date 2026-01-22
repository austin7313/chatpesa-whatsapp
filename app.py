from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime
import requests
import base64

app = Flask(__name__)
CORS(app)

# -------------------------
# CONFIG
# -------------------------
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_ENV = "sandbox"  # change to "production" in prod

# In-memory orders (replace with DB in prod)
orders = {}

# -------------------------
# UTILITIES
# -------------------------
def generate_order_id():
    return f"CP{random.randint(100000, 999999)}"

def get_mpesa_token():
    url = (
        "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        if MPESA_ENV=="sandbox"
        else "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    )
    auth = base64.b64encode(f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()).decode()
    r = requests.get(url, headers={"Authorization": f"Basic {auth}"})
    r.raise_for_status()
    return r.json()["access_token"]

def initiate_stk_push(order):
    token = get_mpesa_token()
    url = (
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        if MPESA_ENV=="sandbox"
        else "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    )
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": order["customer_phone"],
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order["customer_phone"],
        "CallBackURL": f"https://yourdomain.com/mpesa/callback",
        "AccountReference": order["id"],
        "TransactionDesc": "Payment for order"
    }
    r = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
    return r.json()

# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", from_number)

        # Parse order
        order_id = generate_order_id()
        order = {
            "id": order_id,
            "customer_phone": from_number,
            "customer_name": profile_name,
            "items": incoming_msg,
            "amount": 1000,
            "status": "CREATED",
            "created_at": datetime.utcnow().isoformat(),
            "receipt": None
        }
        orders[order_id] = order

        resp = MessagingResponse()
        resp.message(
            f"✅ Order created!\nOrder ID: {order_id}\nAmount: KES {order['amount']}\n\nReply PAY to proceed with M-Pesa"
        )
        return str(resp), 200, {"Content-Type": "text/xml"}
    except Exception as e:
        resp = MessagingResponse()
        resp.message(f"❌ Error: {str(e)}")
        return str(resp), 200, {"Content-Type": "text/xml"}

# -------------------------
# PAY COMMAND
# -------------------------
@app.route("/webhook/pay", methods=["POST"])
def pay_command():
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    order_id = request.form.get("OrderID", None)

    if not order_id or order_id not in orders:
        resp = MessagingResponse()
        resp.message("❌ Order not found")
        return str(resp), 200, {"Content-Type": "text/xml"}

    order = orders[order_id]
    if order["status"] == "PAID":
        resp = MessagingResponse()
        resp.message("✅ Order already paid")
        return str(resp), 200, {"Content-Type": "text/xml"}

    # Initiate STK Push
    stk_response = initiate_stk_push(order)
    order["status"] = "AWAITING_PAYMENT"
    resp = MessagingResponse()
    resp.message("📲 M-Pesa STK Push sent. Enter your PIN to complete payment.")
    return str(resp), 200, {"Content-Type": "text/xml"}

# -------------------------
# M-PESA CALLBACK
# -------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    try:
        order_id = data["Body"]["stkCallback"]["CheckoutRequestID"]
        amount = data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"]
        receipt = data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][1]["Value"]
        payer_name = data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][3]["Value"]
        phone = data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][4]["Value"]

        if order_id in orders:
            orders[order_id]["status"] = "PAID"
            orders[order_id]["receipt"] = receipt
            orders[order_id]["customer_name"] = payer_name
            orders[order_id]["customer_phone"] = phone
            orders[order_id]["paid_at"] = datetime.utcnow().isoformat()
        return jsonify({"ResultCode": 0, "ResultDesc": "Success"})
    except Exception as e:
        return jsonify({"ResultCode": 1, "ResultDesc": str(e)})

# -------------------------
# DASHBOARD ORDERS API
# -------------------------
@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": list(orders.values())})

# -------------------------
# HEALTH CHECK
# -------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "chatpesa"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
