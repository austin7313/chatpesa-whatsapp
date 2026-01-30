"""
FlowStack Backend - Fixed app.py
Handles WhatsApp, M-Pesa, Conversations, Orders
Ensures /orders endpoint works safely
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
import traceback

# ============================================================================
# FLASK APP SETUP
# ============================================================================
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================
DATABASE_URL = os.environ.get('DATABASE_URL')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')  # e.g., whatsapp:+14155238886

MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE')
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY')
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL')  # Render URL + /mpesa/callback

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None

# ============================================================================
# DATABASE CONNECTION
# ============================================================================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# ============================================================================
# DASHBOARD / ORDERS ENDPOINT (FIXED)
# ============================================================================
@app.route('/orders', methods=['GET'])
def get_orders():
    """Get all orders safely for dashboard"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Ensure safe columns and COALESCE to avoid 500s
        cursor.execute("""
            SELECT 
                o.id,
                COALESCE(o.customer_name, '') AS name,
                COALESCE(o.phone, '') AS phone,
                COALESCE(o.amount, 0) AS amount,
                COALESCE(o.status, 'PENDING') AS status,
                COALESCE(o.service, '') AS service,
                COALESCE(o.receipt, '') AS receipt,
                o.created_at,
                pi.payment_intent_id,
                COALESCE(c.conversation_id, '') AS conversation_id,
                COALESCE(c.current_state, '') AS conversation_state
            FROM orders o
            LEFT JOIN payment_intents pi ON o.id = pi.order_id
            LEFT JOIN conversations c ON pi.conversation_id = c.conversation_id
            ORDER BY o.created_at DESC
        """)

        orders = cursor.fetchall()
        conn.close()

        result = []
        for o in orders:
            order = dict(o)
            if order['created_at']:
                order['created_at'] = order['created_at'].isoformat()
            result.append(order)

        return jsonify(result), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================================
# SIMPLE HEALTH CHECK
# ============================================================================
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "status": "online",
        "service": "FlowStack Backend",
        "timestamp": datetime.now().isoformat()
    }), 200

# ============================================================================
# RUN SERVER
# ============================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
