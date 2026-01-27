import os
import uuid
import time
import base64
import datetime
import threading
import requests
import psycopg2
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client

# -------------------- CONFIG --------------------

DATABASE_URL = os.getenv("DATABASE_URL")

MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY")
MPESA_CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL")

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")

app = Flask(__name__)
CORS(app)

twilio = Client(TWILIO_SID, TWILIO_AUTH)

# -------------------- DB --------------------

@contextmanager
def get_db():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# -------------------- HELPERS --------------------

def mpesa_token():
    res = requests.get(
        "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET)
    )
    return res.json()["access_token"]

def stk_password():
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    raw = MPESA_SHORTCODE + MPESA_PASSKEY + ts
    return base64.b64encode(raw.encode()).decode(), ts

def typing_delay(seconds=2):
    time.sleep(seconds)

def send_whatsapp(to, msg):
    typing_delay(2)
    twilio.messages.create(
        from_=TWILIO_WHATSAPP,
        to=to,
        body=msg
    )

# -------------------- DB QUERIES --------------------

def create_order(order_id, phone, name, amount):
    with get_db() as db:
        db.cursor().execute("""
            INSERT INTO orders (id, phone, name, amount, status)
            VALUES (%s, %s, %s, %s, 'PENDING')
        """, (order_id, phone, name, amount))

def attach_stk(order_id, checkout, merchant):
    with get_db() as db:
        db.cursor().execute("""
            UPDATE orders
            SET checkout_request_id=%s, merchant_request_id=%s
            WHERE id=%s
        """, (checkout, merchant, order_id))

def mark_paid(checkout, receipt):
    with get_db() as db:
        cur = db.cursor()
        cur.execute("""
            UPDATE orders
            SET status='PAID', mpesa_receipt=%s, updated_at=NOW()
            WHERE checkout_request_id=%s
            RETURNING phone, name, amount
        """, (receipt, checkout))
        return cur.fetchone()

def mark_failed(checkout):
    with get_db() as db:
        db.cursor().execute("""
            UPDATE orders
            SET status='FAILED', updated_at=NOW()
            WHERE checkout_request_id=%s
        """, (checkout,))

def fetch_orders():
    with get_db() as db:
        cur = db.cursor()
        cur.execute("""
            SELECT id, phone, name, amount, status, mpesa_receipt, created_at
            FROM orders
            ORDER BY created_at DESC
        """)
        return cur.fetchall()

# -------------------- ROUTES --------------------

@app.route("/orders")
def orders():
    return jsonify({"status": "ok", "orders": fetch_orders()})

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    phone = request.form.get("From")
    name = request.form.get("ProfileName") or "Customer"
    text = request.form.get("Body", "").strip()

    if not text.isdigit():
        send_whatsapp(phone, "Please enter amount to pay (e.g. 100)")
        return "OK"

    amount = int(text)
    order_id = "CP" + uuid.uuid4().hex[:6].upper()

    create_order(order_id, phone, name, amount)

    password, timestamp = stk_password()
    token = mpesa_token()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone.replace("whatsapp:", ""),
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone.replace("whatsapp:", ""),
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": "ChatPesa Payment"
    }

    res = requests.post(
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        headers={"Authorization": f"Bearer {token}"},
        json=payload
    ).json()

    attach_stk(order_id, res["CheckoutRequestID"], res["MerchantRequestID"])

    send_whatsapp(phone, f"Hi {name}, enter your M-Pesa PIN to complete payment.")

    return "OK"

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json["Body"]["stkCallback"]
    checkout = data["CheckoutRequestID"]

    if data["ResultCode"] == 0:
        receipt = [
            i["Value"] for i in data["CallbackMetadata"]["Item"]
            if i["Name"] == "MpesaReceiptNumber"
        ][0]

        order = mark_paid(checkout, receipt)

        if order:
            send_whatsapp(
                order["phone"],
                f"Payment successful ✅\nAmount: KES {order['amount']}\nReceipt: {receipt}"
            )
    else:
        mark_failed(checkout)

    return jsonify({"ok": True})

# -------------------- START --------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
