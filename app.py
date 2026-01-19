from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import requests
import base64
from datetime import datetime
import logging
import os
import sqlite3

app = Flask(__name__)

# ----------------------------
# M-PESA Production Credentials
# ----------------------------
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"
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
# Database Setup
# ----------------------------
DB_FILE = "chatpesa.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            phone TEXT PRIMARY KEY,
            name TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            amount REAL,
            status TEXT,
            checkout_id TEXT,
            created_at TEXT,
            FOREIGN KEY(phone) REFERENCES customers(phone)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_customer(phone, name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO customers (phone, name) VALUES (?, ?)", (phone, name))
    conn.commit()
    conn.close()

def create_order(phone, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("INSERT INTO orders (phone, amount, status, created_at) VALUES (?, ?, 'pending', ?)", (phone, amount, timestamp))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_payment(order_id, checkout_id=None, status=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if checkout_id:
        c.execute("UPDATE orders SET checkout_id=? WHERE id=?", (checkout_id, order_id))
    if status:
        c.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

def get_order_by_id(order_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, phone, amount, status, checkout_id FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"order_id": row[0], "phone": row[1], "amount": row[2], "status": row[3], "checkout_id": row[4]}
    return None

def get_customer_name(phone):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name FROM customers WHERE phone=?", (phone,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else f"Customer {phone[-4:]}"

# ----------------------------
# M-PESA Functions
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
    incoming_msg = request.form.get("Body", "").strip().lower()
    phone_number = request.form.get("From", "").replace("whatsapp:", "")
    customer_name = request.form.get("ProfileName", f"Customer {phone_number[-4:]}")
    save_customer(phone_number, customer_name)

    resp = MessagingResponse()
    msg = resp.message()

    # Handle "order <amount>"
    if incoming_msg.startswith("order"):
        try:
            amount = float(incoming_msg.split()[1])
            order_id = create_order(phone_number, amount)
            msg.body(f"🧾 Order #{order_id}\nCustomer: {customer_name}\nAmount: KES {amount}\n\nReply: pay {order_id} to pay now.")
        except (IndexError, ValueError):
            msg.body("⚠️ Invalid command. Use: order <amount> (e.g., order 100)")
        return str(resp)

    # Handle "pay <order_id>"
    elif incoming_msg.startswith("pay"):
        try:
            order_id = int(incoming_msg.split()[1])
            order = get_order_by_id(order_id)
            if not order or order["phone"] != phone_number:
                msg.body(f"❌ No order found with ID {order_id}.")
            else:
                try:
                    stk_resp = stk_push(phone_number=f"254{phone_number[-9:]}", amount=order["amount"])
                    update_order_payment(order_id, checkout_id=stk_resp.get("CheckoutRequestID"))
                    msg.body(f"📲 STK push sent!\nOrder #{order_id}\nAmount: KES {order['amount']}\nEnter your M-Pesa PIN to complete payment.")
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
        receipt = ""
        if status == 0:
            for item in result["CallbackMetadata"]["Item"]:
                if item["Name"] == "Amount":
                    amount = item["Value"]
                elif item["Name"] == "PhoneNumber":
                    phone = str(item["Value"])
                elif item["Name"] == "MpesaReceiptNumber":
                    receipt = item["Value"]
            # Update order in DB
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, phone, amount FROM orders WHERE checkout_id=?", (checkout_request_id,))
            row = c.fetchone()
            if row:
                order_id = row[0]
                update_order_payment(order_id, status="paid")
                customer_name = get_customer_name(phone)
                send_whatsapp_message(phone, f"✅ PAYMENT RECEIVED\nOrder #{order_id}\nAmount: KES {amount}\nReceipt: {receipt}\n\nThank you {customer_name} for paying with ChatPESA 🙏")
            conn.close()
        else:
            # Payment failed
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, phone FROM orders WHERE checkout_id=?", (checkout_request_id,))
            row = c.fetchone()
            if row:
                order_id, phone = row
                send_whatsapp_message(phone, f"❌ Payment failed for Order #{order_id}. Please try again.")
            conn.close()
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
