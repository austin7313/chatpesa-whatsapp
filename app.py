"""
ChatPesa Backend - Flask + PostgreSQL
Handles: WhatsApp, M-Pesa, Orders, Dashboard
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import psycopg2.extras
import os
import requests
import base64
from datetime import datetime
import json

# ============================================================================
# FLASK APP SETUP
# ============================================================================

app = Flask(__name__)
CORS(app)

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

DATABASE_URL = os.environ.get('DATABASE_URL')

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')

MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE')
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY')
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL')

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# ============================================================================
# WHATSAPP FUNCTIONS
# ============================================================================

def send_whatsapp_message(to_phone, message):
    if not to_phone.startswith("whatsapp:"):
        to_phone = f"whatsapp:+{to_phone.replace('+','')}"
    try:
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_phone
        )
        print(f"✓ WhatsApp sent to {to_phone}")
    except Exception as e:
        print(f"✗ WhatsApp error: {e}")

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Create conversation if not exists
    cur.execute("SELECT * FROM conversations WHERE customer_phone=%s", (from_number,))
    conv = cur.fetchone()
    if not conv:
        cur.execute("INSERT INTO conversations(customer_phone, current_state) VALUES(%s,'NEW_LEAD') RETURNING conversation_id", (from_number,))
        conv_id = cur.fetchone()["conversation_id"]
        conn.commit()
    else:
        conv_id = conv["conversation_id"]

    # Save incoming message
    cur.execute(
        "INSERT INTO messages(conversation_id,direction,sender_phone,message_body) VALUES(%s,'inbound',%s,%s)",
        (conv_id, from_number, incoming_msg)
    )
    conn.commit()

    # Simple response logic
    response_msg = "Thanks for your message! We'll contact you shortly."
    send_whatsapp_message(from_number, response_msg)

    cur.execute(
        "INSERT INTO messages(conversation_id,direction,sender_phone,message_body) VALUES(%s,'outbound',%s,%s)",
        (conv_id, TWILIO_WHATSAPP_NUMBER, response_msg)
    )
    conn.commit()
    conn.close()

    resp = MessagingResponse()
    resp.message(response_msg)
    return str(resp), 200

# ============================================================================
# ORDERS ENDPOINT
# ============================================================================

@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, customer_name, phone, amount, status, service, receipt, created_at
            FROM orders ORDER BY created_at DESC
        """)
        orders = cur.fetchall()
        for o in orders:
            if o["created_at"]:
                o["created_at"] = o["created_at"].isoformat()
        conn.close()
        return jsonify(orders), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status":"online","service":"ChatPesa Backend","timestamp":datetime.now().isoformat()}), 200

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
