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
# M-PESA Credentials (USE ENV IN PROD)
# ----------------------------
MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY", "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET", "MYRasd2p9gGFcuCR")
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE", "174379")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY", "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282")
MPESA_CALLBACK_URL = os.getenv(
    "MPESA_CALLBACK_URL",
    "https://flowstack-caribou-1.onrender.com/mpesa/callback"
)

MPESA_ENV = os.getenv("MPESA_ENV", "sandbox")

if MPESA_ENV == "sandbox":
    TOKEN_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
else:
    TOKEN_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

# ----------------------------
# Twilio Credentials
# ----------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"  # Twilio Sandbox

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO)

# ----------------------------
# In-memory Orders Store (DB later)
# ----------------------------
orders = {}  # phone -> {order_id, amount, status, checkout_id}

# ----------------------------
# Helpers: M-Pesa
# ----------------------------
def get_access_token():
    auth = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()

    headers = {"Authorization": f"Basic {auth}"}
    resp = requests.get(TOKEN_URL, headers=headers, timeout=30)
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

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

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
        "TransactionDesc": transaction_desc
    }

    logging.info(f"🚀 Sending STK Push: {payload}")

    resp = requests.post(STK_PUSH_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()

# ----------------------------
# WhatsApp Sender
# ----------------------------
def send_whatsapp_message(to, body):
    logging.info(f"📤 Sending WhatsApp to {to}: {body}")
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:+{to}",
        body=body
    )

# ----------------------------
# Health Check (for Render)
# ----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ----------------------------
# WhatsApp Webhook
# ----------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip().lower()
    phone_number = request.form.get("From", "").replace("whatsapp:", "").replace("+", "")

    logging.info(f"📩 WhatsApp from {phone_number}: {incoming_msg}")

    resp = MessagingResponse()
    msg = resp.message()

    if incoming_msg == "order":
        order_id = len(orders) + 1
        amount = 100  # test amount

        orders[phone_number] = {
            "order_id": order_id,
            "amount": amount,
            "status": "pending",
            "checkout_id": None
        }

        msg.body(
            f"✅ Order #{order_id} created.\n"
            f"Amount: KES {amount}\n"
            f"Reply PAY to complete payment."
        )

    elif incoming_msg == "pay":
        if phone_number not in orders:
            msg.body("❌ No order found. Send ORDER first.")
        else:
            order = orders[phone_number]
            try:
                stk_resp = stk_push(
                    phone_number=f"+{phone_number}",
                    amount=order["amount"],
                    account_reference=f"ORDER-{order['order_id']}",
                    transaction_desc="ChatPESA Order"
                )

                order["checkout_id"] = stk_resp.get("CheckoutRequestID")

                msg.body(
                    "📲 Payment request sent to your phone.\n"
                    "Enter your M-Pesa PIN to complete payment."
                )

            except Exception as e:
                logging.error(f"❌ STK Push error: {e}")
                msg.body("❌ Failed to initiate payment. Please try again.")

    else:
        msg.body(
            "👋 Welcome to ChatPESA\n"
            "Type ORDER to create an order."
        )

    return str(resp)

# ----------------------------
# M-Pesa Callback
# ----------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json(force=True, silent=True)
    logging.info(f"🔥 M-PESA CALLBACK RECEIVED: {data}")

    try:
        result = data["Body"]["stkCallback"]
        status = result["ResultCode"]
        checkout_request_id = result["CheckoutRequestID"]

        amount = None
        phone = None

        if status == 0:
            for item in result["CallbackMetadata"]["Item"]:
                if item["Name"] == "Amount":
                    amount = item["Value"]
                elif item["Name"] == "PhoneNumber":
                    phone = str(item["Value"])

            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    order["status"] = "paid"

                    logging.info(
                        f"✅ Payment success for {p} | "
                        f"Order #{order['order_id']} | "
                        f"Amount {amount}"
                    )

                    send_whatsapp_message(
                        p,
                        f"✅ Payment received!\n"
                        f"Order #{order['order_id']} confirmed.\n"
                        f"Amount: KES {amount}\n"
                        f"Thank you 🙏"
                    )
                    break

        else:
            logging.warning(f"❌ Payment failed: {checkout_request_id}")

            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    send_whatsapp_message(
                        p,
                        f"❌ Payment failed for Order #{order['order_id']}.\n"
                        f"Reply PAY to try again."
                    )
                    break

    except Exception as e:
        logging.error(f"💥 Error processing callback: {e}")

    # Always ACK Safaricom
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
