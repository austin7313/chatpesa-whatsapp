import os
import logging
from flask import Flask, request, jsonify
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from twilio.rest import Client

# -------------------------
# CONFIG
# -------------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# M-Pesa
MPESA_SHORTCODE = os.environ["MPESA_SHORTCODE"]
MPESA_PASSKEY = os.environ["MPESA_PASSKEY"]
MPESA_CONSUMER_KEY = os.environ["MPESA_CONSUMER_KEY"]
MPESA_CONSUMER_SECRET = os.environ["MPESA_CONSUMER_SECRET"]
MPESA_CALLBACK_URL = os.environ["MPESA_CALLBACK_URL"]
MPESA_BASE = "https://api.safaricom.co.ke"

# Twilio WhatsApp
TWILIO_SID = os.environ["TWILIO_SID"]
TWILIO_AUTH = os.environ["TWILIO_AUTH"]
TWILIO_WHATSAPP_NUMBER = os.environ["TWILIO_WHATSAPP_NUMBER"]

# Database
DATABASE_URL = os.environ["DATABASE_URL"]

# -------------------------
# HELPER FUNCTIONS
# -------------------------
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def send_whatsapp_payment_status(order_id, success, amount):
    """
    Sends WhatsApp message to the user when payment succeeds or fails.
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT phone, customer_name FROM orders WHERE id=%s", (order_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            logging.warning(f"Order {order_id} not found for WhatsApp notification")
            return

        phone, customer_name = row
        phone = phone.replace("whatsapp:", "").replace("+", "")
        client = Client(TWILIO_SID, TWILIO_AUTH)
        message = f"Hello {customer_name}, your payment of KES {amount} was "
        message += "successful ✅" if success else "not successful ❌"
        client.messages.create(
            body=message,
            from_="whatsapp:" + TWILIO_WHATSAPP_NUMBER,
            to="whatsapp:+{}".format(phone)
        )
        logging.info(f"WhatsApp sent to {phone}: {message}")
    except Exception as e:
        logging.exception("Failed to send WhatsApp payment status")

# -------------------------
# DASHBOARD ROUTE
# -------------------------
@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, customer_name, phone, amount, status, created_at, paid_at, mpesa_receipt
            FROM orders
            ORDER BY created_at DESC
        """)
        orders = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"orders": orders, "status": "ok"})
    except Exception as e:
        logging.exception("Failed to fetch orders")
        return jsonify({"error": str(e)}), 500

# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.form
    from_number = data.get("From")
    body = data.get("Body")
    logging.info(f"WhatsApp message from {from_number}: {body}")
    # Here you could trigger a payment prompt
    return "OK", 200

# -------------------------
# M-PESA CALLBACK
# -------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    logging.info(f"MPESA CALLBACK: {data}")

    try:
        body = data.get("Body", {}).get("stkCallback", {})
        checkout_request_id = body.get("CheckoutRequestID")
        result_code = body.get("ResultCode")
        metadata = body.get("CallbackMetadata", {}).get("Item", [])

        amount = None
        mpesa_receipt = None
        for item in metadata:
            if item.get("Name") == "Amount":
                amount = item.get("Value")
            elif item.get("Name") == "MpesaReceiptNumber":
                mpesa_receipt = item.get("Value")

        conn = get_db()
        cur = conn.cursor()
        if result_code == 0:
            cur.execute(
                "UPDATE orders SET status=%s, paid_at=NOW(), mpesa_receipt=%s WHERE id=%s",
                ("PAID", mpesa_receipt, checkout_request_id)
            )
            conn.commit()
            send_whatsapp_payment_status(checkout_request_id, True, amount)
        else:
            cur.execute(
                "UPDATE orders SET status=%s WHERE id=%s",
                ("FAILED", checkout_request_id)
            )
            conn.commit()
            send_whatsapp_payment_status(checkout_request_id, False, amount)
        cur.close()
        conn.close()
    except Exception as e:
        logging.exception("Failed to process MPESA callback")

    return jsonify({"status": "ok"})

# -------------------------
# HEALTH CHECK
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# -------------------------
# RUN APP
# -------------------------
if __name__ == "__main__":
    logging.info("Starting ChatPesa app...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
