from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import requests
import base64
from datetime import datetime
import logging
import os

app = Flask(__name__)
CORS(app)  # <-- allows frontend to fetch

# ----------------------------
# M-PESA Credentials
# ----------------------------
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_SHORTCODE = "4031193"  # Production Paybill
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"
MPESA_ENV = "production"

if MPESA_ENV == "sandbox":
    TOKEN_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
else:
    TOKEN_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

# ----------------------------
# Twilio WhatsApp
# ----------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"  # Sandbox number

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO, filename="mpesa_bot.log")

# ----------------------------
# In-memory storage (replace with DB in prod)
# ----------------------------
orders = {}  # phone_number -> {order_id, amount, status, checkout_id, receipt, time}

# ----------------------------
# Helper functions
# ----------------------------
def get_access_token():
    auth = base64.b64encode(f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    resp = requests.get(TOKEN_URL, headers=headers)
    resp.raise_for_status()
    return resp.json()["access_token"]

def generate_password():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    data = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    encoded = base64.b64encode(data.encode()).decode()
    return encoded, timestamp

def stk_push(phone_number, amount, account_reference="ChatPESA", transaction_desc="Payment"):
    token = get_access_token()
    password, timestamp = generate_password()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc
    }
    resp = requests.post(STK_PUSH_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()

def send_whatsapp_message(to, body):
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:+{to}",
        body=body
    )

# ----------------------------
# Endpoints
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status":"ok","message":"Backend live"})

@app.route("/orders", methods=["GET"])
def get_orders():
    results = []
    for phone, order in orders.items():
        results.append({
            "order_id": order["order_id"],
            "phone": phone,
            "amount": order["amount"],
            "status": order["status"],
            "receipt": order.get("receipt",""),
            "time": order.get("time","")
        })
    return jsonify({"orders": results, "status": "ok"})

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip().lower()
    phone_number = request.form.get("From", "").replace("whatsapp:", "")

    resp = MessagingResponse()
    msg = resp.message()

    if "order" in incoming_msg:
        order_id = len(orders) + 1
        try:
            amount = int(incoming_msg.split()[1])
        except:
            amount = 100
        orders[phone_number] = {
            "order_id": order_id,
            "amount": amount,
            "status": "pending",
            "checkout_id": None,
            "receipt": "",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        msg.body(f"🧾 Order #{order_id} created\nAmount: KES {amount}\nReply: pay {order_id} to pay now.")
    elif "pay" in incoming_msg:
        try:
            order_id = int(incoming_msg.split()[1])
            order = None
            for o in orders.values():
                if o["order_id"] == order_id:
                    order = o
                    break
            if not order:
                msg.body("Order not found.")
            else:
                stk_resp = stk_push(phone_number=f"+{phone_number}", amount=order["amount"])
                order["checkout_id"] = stk_resp.get("CheckoutRequestID")
                msg.body(f"📲 STK push sent!\nOrder #{order_id}\nAmount: KES {order['amount']}\nEnter your M-Pesa PIN to complete payment.")
        except Exception as e:
            msg.body(f"❌ Failed to initiate payment. {e}")
    else:
        msg.body("Welcome to ChatPESA. Type 'order <amount>' to create an order.")

    return str(resp)

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    logging.info(f"Callback received: {data}")

    try:
        result = data["Body"]["stkCallback"]
        status = result["ResultCode"]
        checkout_request_id = result["CheckoutRequestID"]
        amount = 0
        phone = ""
        if status == 0:
            for item in result["CallbackMetadata"]["Item"]:
                if item["Name"] == "Amount":
                    amount = item["Value"]
                elif item["Name"] == "PhoneNumber":
                    phone = str(item["Value"])
            # Update order
            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    order["status"] = "paid"
                    order["receipt"] = result.get("MpesaReceiptNumber","")
                    logging.info(f"Payment successful for {p}: amount {amount}")
                    send_whatsapp_message(p, f"✅ PAYMENT RECEIVED\nOrder #{order['order_id']}\nAmount: KES {amount}\nReceipt: {order['receipt']}\nThank you for paying with ChatPesa 🙏")
                    break
        else:
            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    send_whatsapp_message(p, f"❌ Payment failed for Order #{order['order_id']}. Please try again.")
                    break
    except Exception as e:
        logging.error(f"Error processing callback: {e}")

    return jsonify({"ResultCode":0,"ResultDesc":"Received successfully"}), 200

# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
