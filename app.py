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
# M-PESA Credentials (use env in production!)
# ----------------------------
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_SHORTCODE = "174379"  # Example Paybill / Till
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CALLBACK_URL = "https://flowstack-caribou-1.onrender.com/mpesa/callback"
MPESA_ENV = "sandbox"  # "sandbox" or "production"

if MPESA_ENV == "sandbox":
    TOKEN_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
else:
    TOKEN_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

# ----------------------------
# Twilio Credentials (WhatsApp)
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
orders = {}  # phone_number -> {order_id, amount, status, checkout_id}

# ----------------------------
# M-PESA Helper Functions
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

# ----------------------------
# WhatsApp Message Sender
# ----------------------------
def send_whatsapp_message(to, body):
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:+{to}",
        body=body
    )

# ----------------------------
# WhatsApp Webhook
# ----------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip().lower()
    phone_number = request.form.get("From", "").replace("whatsapp:", "")

    resp = MessagingResponse()
    msg = resp.message()

    if "order" in incoming_msg:
        order_id = len(orders) + 1
        amount = 100  # Example amount
        orders[phone_number] = {"order_id": order_id, "amount": amount, "status": "pending", "checkout_id": None}
        msg.body(f"Order #{order_id} created. Amount KES {amount}. Reply 'pay' to pay now.")
    elif "pay" in incoming_msg:
        if phone_number not in orders:
            msg.body("No order found. Please create an order first.")
        else:
            order = orders[phone_number]
            try:
                stk_resp = stk_push(phone_number=f"+{phone_number}", amount=order["amount"])
                order["checkout_id"] = stk_resp.get("CheckoutRequestID")
                msg.body("STK Push sent! Complete payment on your phone. You will receive confirmation automatically once paid.")
            except Exception as e:
                msg.body(f"Error initiating payment: {e}")
    else:
        msg.body("Welcome to ChatPESA. Type 'order' to create an order.")

    return str(resp)

# ----------------------------
# M-PESA Callback
# ----------------------------
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
            # Find order and update
            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    order["status"] = "paid"
                    logging.info(f"Payment successful for {p}: amount {amount}")
                    # Auto-confirm WhatsApp message
                    send_whatsapp_message(p, f"Payment of KES {amount} received! Order #{order['order_id']} confirmed. Thank you!")
                    break
        else:
            logging.warning(f"Payment failed for CheckoutRequestID: {checkout_request_id}")
            # Optional: Notify user of failure
            for p, order in orders.items():
                if order["checkout_id"] == checkout_request_id:
                    send_whatsapp_message(p, f"Payment failed for Order #{order['order_id']}. Please try again.")
                    break
    except Exception as e:
        logging.error(f"Error processing callback: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Received successfully"}), 200

# ----------------------------
# Run App
# ----------------------------
if __name__ == "__main__":
    app.run(port=5000)
