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
# M-PESA Production Credentials
# ----------------------------
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"
MPESA_ENV = "production"  # production endpoint

TOKEN_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

# ----------------------------
# Twilio WhatsApp Credentials
# ----------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO, filename="mpesa_bot.log")

# ----------------------------
# In-memory storage (replace with DB later)
# ----------------------------
orders = {}       # phone_number -> {order_id, amount, status, checkout_id, customer_name}
order_counter = 1 # global order numbering

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
# WhatsApp Messaging
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
    global order_counter
    incoming_msg = request.form.get("Body", "").strip().lower()
    phone_number = request.form.get("From", "").replace("whatsapp:", "")
    customer_name = request.form.get("ProfileName", f"Customer {phone_number[-4:]}")

    resp = MessagingResponse()
    msg = resp.message()

    # Initialize customer order storage
    if phone_number not in orders:
        orders[phone_number] = {"customer_name": customer_name, "orders": {}}

    # Handle "order <amount>"
    if incoming_msg.startswith("order"):
        try:
            amount = float(incoming_msg.split()[1])
            current_order_id = order_counter
            order_counter += 1
            orders[phone_number]["orders"][current_order_id] = {
                "order_id": current_order_id,
                "amount": amount,
                "status": "pending",
                "checkout_id": None
            }
            msg.body(f"🧾 Order #{current_order_id}\nCustomer: {customer_name}\nAmount: KES {amount}\n\nReply: pay {current_order_id} to pay now.")
        except (IndexError, ValueError):
            msg.body("⚠️ Invalid command. Use: order <amount> (e.g., order 100)")
        return str(resp)

    # Handle "pay <order_id>"
    elif incoming_msg.startswith("pay"):
        try:
            order_id = int(incoming_msg.split()[1])
            if order_id not in orders[phone_number]["orders"]:
                msg.body(f"❌ No order found with ID {order_id}. Please create an order first.")
            else:
                order = orders[phone_number]["orders"][order_id]
                try:
                    stk_resp = stk_push(phone_number=f"254{phone_number[-9:]}", amount=order["amount"])
                    order["checkout_id"] = stk_resp.get("CheckoutRequestID")
                    msg.body(f"📲 STK push sent!\n\nOrder #{order_id}\nAmount: KES {order['amount']}\nEnter your M-Pesa PIN to complete payment.")
                except Exception as e:
                    msg.body(f"❌ Failed to initiate payment: {e}")
        except (IndexError, ValueError):
            msg.body("⚠️ Invalid command. Use: pay <order_id> (e.g., pay 1)")
        return str(resp)

    else:
        msg.body("Welcome to ChatPESA. Type 'order <amount>' to create an order.")
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
            for p, cust in orders.items():
                for oid, order in cust["orders"].items():
                    if order["checkout_id"] == checkout_request_id:
                        order["status"] = "paid"
                        logging.info(f"Payment successful for {p}: amount {amount}")
                        send_whatsapp_message(p, f"✅ PAYMENT RECEIVED\nOrder #{oid}\nAmount: KES {amount}\nReceipt: {result.get('CallbackMetadata', {}).get('Item', [{}])[0].get('Value', '')}\n\nThank you for paying with ChatPESA 🙏")
                        break
        else:
            logging.warning(f"Payment failed for CheckoutRequestID: {checkout_request_id}")
            # Notify user of failure
            for p, cust in orders.items():
                for oid, order in cust["orders"].items():
                    if order["checkout_id"] == checkout_request_id:
                        send_whatsapp_message(p, f"❌ Payment failed for Order #{oid}. Please try again.")
                        break
    except Exception as e:
        logging.error(f"Error processing callback: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Received successfully"}), 200

# ----------------------------
# Health Check
# ----------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "endpoints": ["/health","/webhook/whatsapp","/mpesa/callback"],
        "service": "ChatPESA WhatsApp Payments",
        "status": "running"
    })

# ----------------------------
# Run App
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
