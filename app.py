from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import requests
import base64
from datetime import datetime
import logging
import os

app = Flask(__name__)

# ----------------------------
# CONFIG
# ----------------------------
MPESA_ENV = "production"  # sandbox | production

MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

if MPESA_ENV == "sandbox":
    TOKEN_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
else:
    TOKEN_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

# ----------------------------
# TWILIO CONFIG
# ----------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ----------------------------
# LOGGING
# ----------------------------
logging.basicConfig(level=logging.INFO)

# ----------------------------
# IN-MEMORY ORDERS (REPLACE WITH DB LATER)
# ----------------------------
orders = {}  # phone -> {order_id, amount, status, checkout_id, receipt}

# ----------------------------
# HELPERS
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

def stk_push(phone_number, amount, account_reference):
    token = get_access_token()
    password, timestamp = generate_password()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": "ChatPesa Payment"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    resp = requests.post(STK_PUSH_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()

def send_whatsapp_message(to, body):
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{to}",
        body=body
    )

# ----------------------------
# ROUTES
# ----------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "ChatPesa WhatsApp Payments",
        "status": "running",
        "endpoints": [
            "/health",
            "/webhook/whatsapp",
            "/mpesa/callback"
        ]
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ----------------------------
# WHATSAPP WEBHOOK
# ----------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip().lower()
    from_number = request.form.get("From", "").replace("whatsapp:", "")

    resp = MessagingResponse()
    msg = resp.message()

    if incoming_msg.startswith("order"):
        parts = incoming_msg.split()
        if len(parts) == 2 and parts[1].isdigit():
            amount = int(parts[1])
        else:
            amount = 100

        order_id = len(orders) + 1
        orders[from_number] = {
            "order_id": order_id,
            "amount": amount,
            "status": "pending",
            "checkout_id": None,
            "receipt": None
        }

        msg.body(
            f"🧾 Order #{order_id} created\n"
            f"Amount: KES {amount}\n\n"
            f"Reply: pay {order_id} to pay now."
        )

    elif incoming_msg.startswith("pay"):
        parts = incoming_msg.split()
        if len(parts) != 2 or not parts[1].isdigit():
            msg.body("❌ Invalid format. Use: pay 1")
        else:
            order_id = int(parts[1])
            order = None

            for p, o in orders.items():
                if p == from_number and o["order_id"] == order_id:
                    order = o
                    break

            if not order:
                msg.body("❌ Order not found.")
            elif order["status"] == "paid":
                msg.body("✅ This order is already paid.")
            else:
                try:
                    stk_resp = stk_push(
                        phone_number=from_number,
                        amount=order["amount"],
                        account_reference=f"ORDER{order_id}"
                    )

                    order["checkout_id"] = stk_resp.get("CheckoutRequestID")

                    msg.body(
                        f"📲 STK push sent!\n\n"
                        f"Order #{order_id}\n"
                        f"Amount: KES {order['amount']}\n\n"
                        f"Enter your M-Pesa PIN to complete payment."
                    )

                except Exception as e:
                    logging.error(e)
                    msg.body("❌ Failed to initiate payment. Try again.")

    else:
        msg.body(
            "👋 Welcome to ChatPesa\n\n"
            "Create order: order 10\n"
            "Pay order: pay 1"
        )

    return str(resp)

# ----------------------------
# M-PESA CALLBACK
# ----------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    logging.info(f"📥 Callback: {data}")

    try:
        result = data["Body"]["stkCallback"]
        status = result["ResultCode"]
        checkout_request_id = result["CheckoutRequestID"]

        if status == 0:
            amount = None
            receipt = None
            phone = None

            for item in result["CallbackMetadata"]["Item"]:
                if item["Name"] == "Amount":
                    amount = item["Value"]
                elif item["Name"] == "MpesaReceiptNumber":
                    receipt = item["Value"]
                elif item["Name"] == "PhoneNumber":
                    phone = str(item["Value"])

            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    order["status"] = "paid"
                    order["receipt"] = receipt

                    logging.info(f"✅ PAID | {p} | Order #{order['order_id']} | {receipt}")

                    send_whatsapp_message(
                        p,
                        f"✅ PAYMENT RECEIVED\n"
                        f"Order #{order['order_id']}\n"
                        f"Amount: KES {amount}\n"
                        f"Receipt: {receipt}\n\n"
                        f"Thank you for paying with ChatPesa 🙏"
                    )
                    break

        else:
            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    order["status"] = "failed"
                    send_whatsapp_message(
                        p,
                        f"❌ PAYMENT FAILED\n"
                        f"Order #{order['order_id']}\n"
                        f"Please try again."
                    )
                    break

    except Exception as e:
        logging.error(f"❌ Callback error: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Received successfully"}), 200

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
