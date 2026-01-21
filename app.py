from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random
import requests
import base64

app = Flask(__name__)

# In-memory storage (replace with your DB)
orders = []

# Business / M-Pesa config
BUSINESS = {
    "name": "ChatPesa",
    "shortcode": "4031193",
    "passkey": "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282",
    "consumer_key": "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP",
    "consumer_secret": "MYRasd2p9gGFcuCR",
    "callback_url": "https://chatpesa-whatsapp.onrender.com/mpesa/callback",
}

def generate_order_id():
    return f"ORD{random.randint(1000,9999)}"

def parse_message(msg):
    msg_lower = msg.lower()
    items = []
    amount = 0

    if "donate" in msg_lower:
        items.append("Donation")
        amount = int(''.join(filter(str.isdigit, msg_lower)) or 500)
    elif "ticket" in msg_lower:
        items.append("Ticket")
        amount = int(''.join(filter(str.isdigit, msg_lower)) or 1000)
    elif msg_lower.strip():
        items.append("Custom Order")
        amount = int(''.join(filter(str.isdigit, msg_lower)) or 1000)
    else:
        items.append("Custom Order")
        amount = 1000

    return {"items": " + ".join(items), "amount": amount}

# ------------------------
# WhatsApp Webhook
# ------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")

    order_details = parse_message(incoming_msg)
    order_id = generate_order_id()

    order_data = {
        "id": order_id,
        "customer_name": profile_name,
        "customer_phone": from_number,
        "items": order_details["items"],
        "amount": order_details["amount"],
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.utcnow().isoformat()
    }

    orders.append(order_data)

    # Initiate M-Pesa STK Push
    try:
        token_res = requests.get(
            "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
            auth=(BUSINESS["consumer_key"], BUSINESS["consumer_secret"])
        )
        token = token_res.json()["access_token"]
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        password_str = BUSINESS["shortcode"] + BUSINESS["passkey"] + timestamp
        password = base64.b64encode(password_str.encode()).decode("utf-8")

        stk_payload = {
            "BusinessShortCode": BUSINESS["shortcode"],
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": order_details["amount"],
            "PartyA": from_number.replace("+", ""),
            "PartyB": BUSINESS["shortcode"],
            "PhoneNumber": from_number.replace("+", ""),
            "CallBackURL": BUSINESS["callback_url"],
            "AccountReference": order_id,
            "TransactionDesc": order_details["items"]
        }

        headers = {"Authorization": f"Bearer {token}"}
        # Uncomment to send real request
        # requests.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest", json=stk_payload, headers=headers)
    except Exception as e:
        print("⚠️ STK Push failed:", e)

    resp = MessagingResponse()
    resp.message(
        f"✅ {BUSINESS['name']} received your order/donation!\n\n"
        f"Items: {order_details['items']}\n"
        f"Amount: KES {order_details['amount']}\n"
        f"Order ID: {order_id}\n"
        f"You will receive a payment prompt shortly."
    )
    return str(resp), 200, {'Content-Type': 'text/xml'}

# ------------------------
# M-Pesa Callback
# ------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    try:
        # Extract payment info (simplified)
        transaction_id = data.get("Body", {}).get("stkCallback", {}).get("CheckoutRequestID", "")
        result_code = data.get("Body", {}).get("stkCallback", {}).get("ResultCode", 1)
        amount = data.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {}).get("Item", [{}])[0].get("Value", 0)
        phone = data.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {}).get("Item", [{}])[1].get("Value", "")
        customer_name = data.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {}).get("Item", [{}])[2].get("Value", "Customer")

        # Find order
        for order in orders:
            if order["id"] == transaction_id:
                order["status"] = "PAID" if result_code == 0 else "FAILED"
                order["amount"] = amount
                order["customer_name"] = customer_name
                order["customer_phone"] = phone
                order["paid_at"] = datetime.utcnow().isoformat()
                break
    except Exception as e:
        print("⚠️ Callback processing error:", e)
    return jsonify({"status": "ok"})

# ------------------------
# Orders API
# ------------------------
@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": orders})

# ------------------------
# Health Check
# ------------------------
@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(debug=True)
