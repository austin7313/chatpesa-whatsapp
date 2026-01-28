import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from twilio.rest import Client
from datetime import datetime
import base64

app = Flask(__name__)
CORS(app)

# -----------------------
# Environment Variables
# -----------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")

MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL")
MPESA_BASE = "https://api.safaricom.co.ke"

if not all([
    DATABASE_URL, TWILIO_SID, TWILIO_AUTH, TWILIO_WHATSAPP_NUMBER,
    MPESA_SHORTCODE, MPESA_PASSKEY, MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_CALLBACK_URL
]):
    raise RuntimeError("❌ One or more required environment variables are missing!")

# -----------------------
# Twilio Client
# -----------------------
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# -----------------------
# DB Helpers
# -----------------------
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer_name TEXT,
            phone TEXT,
            amount NUMERIC,
            service_requested TEXT,
            status TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# -----------------------
# Utils
# -----------------------
def normalize_phone(phone):
    """Convert phone to format +2547xxxxxxx"""
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith("0"):
        return "+254" + digits[1:]
    elif digits.startswith("254"):
        return "+" + digits
    elif digits.startswith("+254"):
        return digits
    else:
        return "+" + digits

def send_whatsapp(to, message):
    twilio_client.messages.create(
        from_="whatsapp:" + TWILIO_WHATSAPP_NUMBER,
        body=message,
        to="whatsapp:" + to
    )

# -----------------------
# MPESA Helpers
# -----------------------
def get_mpesa_token():
    auth = base64.b64encode(f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()).decode()
    res = requests.get(f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
                       headers={"Authorization": f"Basic {auth}"})
    res.raise_for_status()
    return res.json()["access_token"]

def initiate_stk_push(phone, amount, account_ref):
    token = get_mpesa_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password_str = MPESA_SHORTCODE + MPESA_PASSKEY + timestamp
    password = base64.b64encode(password_str.encode()).decode()
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": account_ref,
        "TransactionDesc": f"Payment for {account_ref}"
    }
    res = requests.post(f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
                        headers={"Authorization": f"Bearer {token}"}, json=payload)
    res.raise_for_status()
    return res.json()

# -----------------------
# Routes
# -----------------------
@app.route("/orders", methods=["GET"])
def get_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC;")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "orders": orders})

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.form
    from_number = normalize_phone(data.get("From", ""))
    body = data.get("Body", "").strip()
    name = "WhatsApp User"  # optional, could parse if Twilio provides
    amount = 10  # default amount, or parse from message
    service_requested = body  # save full message as service requested
    account_ref = f"CP{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Save order as PENDING
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (customer_name, phone, amount, service_requested, status)
        VALUES (%s, %s, %s, %s, %s) RETURNING id;
    """, (name, from_number, amount, service_requested, "PENDING"))
    order_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    # Reply immediately
    send_whatsapp(from_number, f"✅ Order received! Ref: {account_ref}\nService: {service_requested}\nYou will receive an STK prompt shortly.")

    # Initiate STK Push
    try:
        stk_res = initiate_stk_push(from_number, amount, account_ref)
        print("STK Initiated:", stk_res)
    except Exception as e:
        print("STK Push Error:", e)
        send_whatsapp(from_number, "❌ STK push failed, please try again later.")

    return "OK", 200

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    if not data:
        return "No data", 400

    result = data.get("Body", {}).get("stkCallback", {})
    account_ref = result.get("CheckoutRequestID") or result.get("MerchantRequestID")
    status = result.get("ResultCode")
    receipt = result.get("CallbackMetadata", {}).get("Item", [{}])
    receipt_number = next((i["Value"] for i in receipt if i.get("Name") == "MpesaReceiptNumber"), None)
    amount = next((i["Value"] for i in receipt if i.get("Name") == "Amount"), None)
    phone = next((i["Value"] for i in receipt if i.get("Name") == "PhoneNumber"), None)

    if status == 0:
        # Paid
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE orders
            SET status = 'PAID', mpesa_receipt=%s, paid_at=NOW()
            WHERE phone=%s AND status='PENDING'
            ORDER BY created_at DESC
            LIMIT 1;
        """, (receipt_number, normalize_phone(str(phone))))
        conn.commit()
        cur.close()
        conn.close()

        # Send WhatsApp confirmation
        send_whatsapp(normalize_phone(str(phone)),
                      f"✅ Payment received!\nRef: {receipt_number}\nAmount: KES {amount}")

    return jsonify({"status": "ok"}), 200

# -----------------------
# Start
# -----------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
