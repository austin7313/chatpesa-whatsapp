from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import requests, base64, os, datetime, sqlite3, uuid

app = Flask(__name__)
CORS(app)

# --------------------
# CONFIG (ENV ONLY)
# --------------------
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
MPESA_CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL")

# --------------------
# DATABASE
# --------------------
conn = sqlite3.connect("orders.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_phone TEXT,
    customer_name TEXT,
    items TEXT,
    amount INTEGER,
    status TEXT,
    mpesa_receipt TEXT,
    paid_at TEXT,
    created_at TEXT
)
""")
conn.commit()

# --------------------
# HELPERS
# --------------------
def mpesa_access_token():
    r = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET),
    )
    return r.json()["access_token"]

def stk_push(phone, amount, order_id):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

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
        "AccountReference": order_id,
        "TransactionDesc": "ChatPesa Payment"
    }

    headers = {
        "Authorization": f"Bearer {mpesa_access_token()}",
        "Content-Type": "application/json"
    }

    requests.post(
        "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers
    )

# --------------------
# WHATSAPP WEBHOOK
# --------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get("Body", "").strip().lower()
    phone = request.form.get("From").replace("whatsapp:", "")
    resp = MessagingResponse()

    if msg.startswith("pay"):
        order_id = msg.replace("pay", "").strip()

        cur.execute("SELECT amount FROM orders WHERE id=?", (order_id,))
        row = cur.fetchone()

        if not row:
            resp.message("Order not found.")
            return str(resp)

        stk_push(phone, row[0], order_id)
        resp.message("M-Pesa payment request sent. Enter your PIN.")
        return str(resp)

    # CREATE ORDER
    amount = int("".join(filter(str.isdigit, msg)) or 0)
    if amount <= 0:
        resp.message("Send amount to create order. Example: 1500")
        return str(resp)

    order_id = f"RCP{uuid.uuid4().hex[:6].upper()}"
    now = datetime.datetime.now().isoformat()

    cur.execute("""
        INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        order_id, phone, phone, "Custom Order",
        amount, "AWAITING_PAYMENT", None, None, now
    ))
    conn.commit()

    resp.message(
        f"Order ID: {order_id}\n"
        f"Amount: KES {amount}\n"
        f"Reply: PAY {order_id} to pay"
    )
    return str(resp)

# --------------------
# M-PESA CALLBACK
# --------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    result = data["Body"]["stkCallback"]

    if result["ResultCode"] != 0:
        return jsonify({"ok": True})

    meta = {i["Name"]: i.get("Value") for i in result["CallbackMetadata"]["Item"]}

    receipt = meta["MpesaReceiptNumber"]
    amount = meta["Amount"]
    phone = meta["PhoneNumber"]
    paid_at = meta["TransactionDate"]

    order_id = result["MerchantRequestID"] or result["CheckoutRequestID"]

    cur.execute("""
        UPDATE orders
        SET status='PAID',
            mpesa_receipt=?,
            customer_name=?,
            paid_at=?
        WHERE id=? AND status!='PAID'
    """, (
        receipt,
        meta.get("FirstName", phone),
        paid_at,
        order_id
    ))
    conn.commit()

    return jsonify({"ok": True})

# --------------------
# DASHBOARD API
# --------------------
@app.route("/orders")
def orders():
    cur.execute("""
        SELECT id, customer_name, items, amount, status, created_at
        FROM orders
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()

    return jsonify({
        "status": "ok",
        "orders": [
            {
                "id": r[0],
                "customer_name": r[1],
                "items": r[2],
                "amount": r[3],
                "status": r[4],
                "created_at": r[5]
            } for r in rows
        ]
    })

@app.route("/")
def health():
    return "ChatPesa API ONLINE"
