import os
import base64
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# ------------------ APP SETUP ------------------
app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE")  # PAYBILL
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL")

# ------------------ DB ------------------
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            phone TEXT,
            amount TEXT,
            status TEXT,
            mpesa_receipt TEXT,
            customer_name TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

# ------------------ HELPERS ------------------
def normalize_msisdn(phone: str) -> str:
    """
    Converts:
    whatsapp:+2547xxxxxxx → 2547xxxxxxx
    +2547xxxxxxx          → 2547xxxxxxx
    07xxxxxxxx            → 2547xxxxxxx
    """
    phone = phone.replace("whatsapp:", "").replace("+", "").strip()
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    return phone

def mpesa_access_token():
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET), timeout=10)
    return r.json()["access_token"]

# ------------------ STK PUSH ------------------
def send_stk_push(phone, amount, order_id):
    msisdn = normalize_msisdn(phone)
    print("FINAL MSISDN SENT TO STK:", msisdn)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": msisdn,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": msisdn,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": "ChatPesa Payment"
    }

    headers = {
        "Authorization": f"Bearer {mpesa_access_token()}",
        "Content-Type": "application/json"
    }

    r = requests.post(
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers,
        timeout=15
    )

    print("STK RESPONSE:", r.status_code, r.text)
    return r.json()

# ------------------ ROUTES ------------------
@app.route("/stk", methods=["POST"])
def stk():
    data = request.json
    phone = data["phone"]
    amount = data["amount"]
    order_id = data["order_id"]

    try:
        response = send_stk_push(phone, amount, order_id)
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    print("MPESA CALLBACK:", data)

    try:
        result = data["Body"]["stkCallback"]
        if result["ResultCode"] == 0:
            meta = {i["Name"]: i.get("Value") for i in result["CallbackMetadata"]["Item"]}
            receipt = meta.get("MpesaReceiptNumber")
            paid_at = datetime.now()
            amount = meta.get("Amount")
            phone = meta.get("PhoneNumber")
            order_id = result["CheckoutRequestID"]

            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE orders
                SET status='PAID', mpesa_receipt=%s, paid_at=%s
                WHERE id=%s
            """, (receipt, paid_at, order_id))
            conn.commit()
            conn.close()

    except Exception as e:
        print("CALLBACK ERROR:", e)

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

@app.route("/orders", methods=["GET"])
def orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return jsonify({"status": "ok", "orders": rows})

# ------------------ START ------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=10000)
