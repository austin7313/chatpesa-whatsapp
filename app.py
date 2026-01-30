"""
FlowStack Backend - Complete app.py
Python/Flask with PostgreSQL
Handles: WhatsApp, M-Pesa, Conversations, Follow-ups, Orders
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
from datetime import datetime, timedelta
import json

# ============================================================================
# FLASK APP SETUP
# ============================================================================

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

# Database
DATABASE_URL = os.environ.get('DATABASE_URL')

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')  # e.g., whatsapp:+14155238886

# M-Pesa Daraja
MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE')
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY')
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL')  # Your Render URL + /mpesa/callback

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_db_connection():
    """Get PostgreSQL database connection"""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# ============================================================================
# CONVERSATION MANAGEMENT
# ============================================================================

def get_or_create_conversation(phone_number):
    """
    Get existing conversation or create new one
    Returns: dict with conversation_id, customer_name, current_state
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Normalize phone number (remove 'whatsapp:' prefix if present)
    clean_phone = phone_number.replace('whatsapp:', '').replace('+', '')
    
    # Try to find existing conversation
    cursor.execute("""
        SELECT conversation_id, customer_name, current_state, follow_up_count
        FROM conversations
        WHERE customer_phone = %s
    """, (clean_phone,))
    
    result = cursor.fetchone()
    
    if result:
        # Existing conversation found
        conversation = dict(result)
        conn.close()
        return conversation
    else:
        # Create new conversation
        cursor.execute("""
            INSERT INTO conversations (customer_phone, current_state)
            VALUES (%s, 'NEW_LEAD')
            RETURNING conversation_id, customer_name, current_state, follow_up_count
        """, (clean_phone,))
        
        new_conversation = dict(cursor.fetchone())
        conn.commit()
        conn.close()
        
        # Emit NEW_LEAD event (for future event bus)
        print(f"✓ New conversation created: {new_conversation['conversation_id']}")
        
        return new_conversation

def save_message(conversation_id, direction, sender_phone, message_body):
    """
    Save message to conversation history
    direction: 'inbound' or 'outbound'
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    clean_phone = sender_phone.replace('whatsapp:', '').replace('+', '')
    
    cursor.execute("""
        INSERT INTO messages (conversation_id, direction, sender_phone, message_body)
        VALUES (%s, %s, %s, %s)
    """, (conversation_id, direction, clean_phone, message_body))
    
    conn.commit()
    conn.close()

def update_conversation_activity(conversation_id, is_customer_message=True):
    """Update conversation last message timestamp"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_customer_message:
        cursor.execute("""
            UPDATE conversations
            SET last_message_at = NOW(),
                last_customer_message_at = NOW()
            WHERE conversation_id = %s
        """, (conversation_id,))
    else:
        cursor.execute("""
            UPDATE conversations
            SET last_message_at = NOW()
            WHERE conversation_id = %s
        """, (conversation_id,))
    
    conn.commit()
    conn.close()

def update_conversation_state(conversation_id, new_state):
    """Update conversation state"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE conversations
        SET current_state = %s,
            previous_state = current_state
        WHERE conversation_id = %s
    """, (new_state, conversation_id))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Conversation {conversation_id} state changed to {new_state}")

def extract_customer_name(message_text, conversation_id):
    """
    Extract customer name from message if asking for it
    Simple keyword detection (can be enhanced with AI)
    """
    message_lower = message_text.lower()
    
    # Check if this might be a name response
    # (comes after asking "what's your name?")
    if len(message_text.split()) <= 3 and not any(word in message_lower for word in ['hi', 'hello', 'yes', 'no', 'ok']):
        # Likely a name
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE conversations
            SET customer_name = %s
            WHERE conversation_id = %s
        """, (message_text.title(), conversation_id))
        
        conn.commit()
        conn.close()
        
        return message_text.title()
    
    return None

# ============================================================================
# FOLLOW-UP SYSTEM
# ============================================================================

def schedule_follow_up(conversation_id, trigger_reason='no_reply_2hr', hours_delay=2):
    """Schedule a follow-up task"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if follow-up already scheduled
    cursor.execute("""
        SELECT task_id FROM follow_up_tasks
        WHERE conversation_id = %s AND status = 'pending'
    """, (conversation_id,))
    
    if cursor.fetchone():
        conn.close()
        return  # Already scheduled
    
    # Determine message based on trigger
    if trigger_reason == 'no_reply_2hr':
        message = "Hi again! Just checking if you still need help with your order? 😊"
    elif trigger_reason == 'no_reply_24hr':
        message = "Hello! We noticed you haven't replied yet. Are you still interested?"
    elif trigger_reason == 'payment_reminder':
        message = "Hi! Just a reminder - your payment is still pending. Let us know if you need help!"
    else:
        message = "Hi! Following up on your order. Still interested?"
    
    # Schedule follow-up
    cursor.execute("""
        INSERT INTO follow_up_tasks (
            conversation_id,
            trigger_reason,
            scheduled_time,
            message_body
        ) VALUES (%s, %s, NOW() + INTERVAL '%s hours', %s)
    """, (conversation_id, trigger_reason, hours_delay, message))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Follow-up scheduled for conversation {conversation_id} in {hours_delay} hours")

def cancel_pending_followups(conversation_id):
    """Cancel all pending follow-ups for a conversation"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE follow_up_tasks
        SET status = 'cancelled'
        WHERE conversation_id = %s AND status = 'pending'
    """, (conversation_id,))
    
    conn.commit()
    conn.close()

# ============================================================================
# PAYMENT INTENT SYSTEM
# ============================================================================

def create_payment_intent(conversation_id, amount, service_description):
    """
    Create payment intent (links conversation to upcoming payment)
    Returns: payment_intent_id
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create payment intent
    cursor.execute("""
        INSERT INTO payment_intents (
            conversation_id,
            expected_amount,
            status,
            expires_at,
            service_description
        ) VALUES (%s, %s, 'pending', NOW() + INTERVAL '48 hours', %s)
        RETURNING payment_intent_id
    """, (conversation_id, amount, service_description))
    
    payment_intent_id = cursor.fetchone()[0]
    
    # Update conversation state
    cursor.execute("""
        UPDATE conversations
        SET current_state = 'WAITING_FOR_PAYMENT'
        WHERE conversation_id = %s
    """, (conversation_id,))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Payment intent created: {payment_intent_id} (KES {amount})")
    
    return payment_intent_id

def link_payment_intent_to_order(payment_intent_id, order_id):
    """Link payment intent to order"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE payment_intents
        SET order_id = %s
        WHERE payment_intent_id = %s
    """, (order_id, payment_intent_id))
    
    conn.commit()
    conn.close()

# ============================================================================
# WHATSAPP FUNCTIONS
# ============================================================================

def send_whatsapp_message(to_phone, message_body):
    """Send WhatsApp message via Twilio"""
    try:
        # Ensure phone has whatsapp: prefix
        if not to_phone.startswith('whatsapp:'):
            to_phone = f'whatsapp:+{to_phone}'
        
        message = twilio_client.messages.create(
            body=message_body,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_phone
        )
        
        print(f"✓ WhatsApp sent to {to_phone}: {message.sid}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to send WhatsApp: {e}")
        return False

def handle_customer_message(message_text, conversation):
    """
    Handle incoming customer message and generate response
    This is where you add your business logic
    """
    message_lower = message_text.lower()
    
    # NEW_LEAD state
    if conversation['current_state'] == 'NEW_LEAD':
        if not conversation['customer_name']:
            # Ask for name
            return "Hi! Welcome to our service. What's your name?"
        else:
            # Name already saved, ask what they need
            return f"Hi {conversation['customer_name']}! How can we help you today?"
    
    # ENGAGED state
    elif conversation['current_state'] == 'ENGAGED':
        # Check if customer is providing their name
        name = extract_customer_name(message_text, conversation['conversation_id'])
        if name:
            update_conversation_state(conversation['conversation_id'], 'ENGAGED')
            return f"Nice to meet you, {name}! What can we help you with today?"
        
        # Check for order keywords
        if any(word in message_lower for word in ['order', 'buy', 'purchase', 'need', 'want']):
            return "Great! What would you like to order? (e.g., 2 Vodka bottles)"
        
        # Generic engaged response
        return "I'd be happy to help! Could you tell me what you're looking for?"
    
    # WAITING_FOR_PAYMENT state
    elif conversation['current_state'] == 'WAITING_FOR_PAYMENT':
        if 'paid' in message_lower or 'sent' in message_lower:
            return "Please share your M-Pesa confirmation code (e.g., QRT45678) so we can verify your payment."
        else:
            return "Your order is ready! Total is KES [amount]. Please complete payment to proceed."
    
    # Default response
    return "Thanks for your message! Our team will assist you shortly."

# ============================================================================
# WEBHOOKS
# ============================================================================

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        
        print(f"📱 WhatsApp message from {from_number}: {incoming_msg}")
        
        # 1. Get or create conversation
        conversation = get_or_create_conversation(from_number)
        
        # 2. Save incoming message
        save_message(
            conversation['conversation_id'],
            'inbound',
            from_number,
            incoming_msg
        )
        
        # 3. Update activity timestamp
        update_conversation_activity(conversation['conversation_id'], is_customer_message=True)
        
        # 4. Generate response
        response_msg = handle_customer_message(incoming_msg, conversation)
        
        # 5. Save outgoing message
        save_message(
            conversation['conversation_id'],
            'outbound',
            TWILIO_WHATSAPP_NUMBER,
            response_msg
        )
        
        # 6. Send response
        resp = MessagingResponse()
        resp.message(response_msg)
        
        # 7. Schedule follow-up if customer stops replying
        schedule_follow_up(conversation['conversation_id'])
        
        return str(resp), 200
        
    except Exception as e:
        print(f"✗ WhatsApp webhook error: {e}")
        return "Error", 500

# ============================================================================
# M-PESA FUNCTIONS
# ============================================================================

def get_mpesa_access_token():
    """Get M-Pesa OAuth access token"""
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    
    credentials = f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded}"
    }
    
    response = requests.get(url, headers=headers)
    return response.json()['access_token']

def initiate_stk_push(phone_number, amount, account_reference, payment_intent_id):
    """
    Initiate M-Pesa STK Push
    Returns: CheckoutRequestID
    """
    access_token = get_mpesa_access_token()
    
    # Generate timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Generate password
    password_str = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode()
    
    # Clean phone number (remove country code if present)
    clean_phone = phone_number.replace('+', '').replace('whatsapp:', '')
    if clean_phone.startswith('254'):
        clean_phone = clean_phone
    elif clean_phone.startswith('0'):
        clean_phone = '254' + clean_phone[1:]
    else:
        clean_phone = '254' + clean_phone
    
    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": clean_phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": clean_phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": f"Payment for {account_reference}"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    result = response.json()
    
    if result.get('ResponseCode') == '0':
        checkout_request_id = result['CheckoutRequestID']
        
        # Store checkout request ID in payment intent
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE payment_intents
            SET mpesa_checkout_id = %s
            WHERE payment_intent_id = %s
        """, (checkout_request_id, payment_intent_id))
        conn.commit()
        conn.close()
        
        print(f"✓ STK Push initiated: {checkout_request_id}")
        return checkout_request_id
    else:
        print(f"✗ STK Push failed: {result}")
        return None

@app.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """Handle M-Pesa payment callback"""
    try:
        data = request.get_json()
        print(f"💰 M-Pesa callback received: {json.dumps(data, indent=2)}")
        
        callback_data = data['Body']['stkCallback']
        result_code = callback_data['ResultCode']
        checkout_request_id = callback_data['CheckoutRequestID']
        
        if result_code == 0:
            # Payment successful
            callback_metadata = callback_data['CallbackMetadata']['Item']
            
            # Extract payment details
            amount = None
            phone = None
            receipt = None
            
            for item in callback_metadata:
                if item['Name'] == 'Amount':
                    amount = item['Value']
                elif item['Name'] == 'MpesaReceiptNumber':
                    receipt = item['Value']
                elif item['Name'] == 'PhoneNumber':
                    phone = item['Value']
            
            # Find payment intent
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    pi.payment_intent_id,
                    pi.conversation_id,
                    pi.order_id,
                    pi.expected_amount,
                    pi.service_description,
                    c.customer_phone,
                    c.customer_name
                FROM payment_intents pi
                JOIN conversations c ON pi.conversation_id = c.conversation_id
                WHERE pi.mpesa_checkout_id = %s
            """, (checkout_request_id,))
            
            intent = cursor.fetchone()
            
            if intent:
                # Update payment intent
                cursor.execute("""
                    UPDATE payment_intents
                    SET status = 'paid',
                        mpesa_receipt = %s,
                        paid_at = NOW()
                    WHERE payment_intent_id = %s
                """, (receipt, intent['payment_intent_id']))
                
                # Update order if linked
                if intent['order_id']:
                    cursor.execute("""
                        UPDATE orders
                        SET status = 'PAID',
                            receipt = %s
                        WHERE id = %s
                    """, (receipt, intent['order_id']))
                
                # Update conversation state
                cursor.execute("""
                    UPDATE conversations
                    SET current_state = 'PAID'
                    WHERE conversation_id = %s
                """, (intent['conversation_id']))
                
                # Cancel pending follow-ups
                cursor.execute("""
                    UPDATE follow_up_tasks
                    SET status = 'cancelled'
                    WHERE conversation_id = %s AND status = 'pending'
                """, (intent['conversation_id']))
                
                conn.commit()
                conn.close()
                
                # Send WhatsApp confirmation
                customer_name = intent['customer_name'] or 'Customer'
                confirmation_msg = f"""✅ Payment Received!

Hi {customer_name}! Your payment has been confirmed.

Amount: KES {amount}
Service: {intent['service_description']}
Receipt: {receipt}

Thank you for your order! We'll process it shortly."""
                
                send_whatsapp_message(intent['customer_phone'], confirmation_msg)
                
                print(f"✓ Payment confirmed: {receipt}")
            else:
                print(f"✗ Payment intent not found for checkout: {checkout_request_id}")
        
        else:
            # Payment failed
            print(f"✗ M-Pesa payment failed: Code {result_code}")
        
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
        
    except Exception as e:
        print(f"✗ M-Pesa callback error: {e}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Failed"}), 500

# ============================================================================
# API ENDPOINTS (For Dashboard)
# ============================================================================

@app.route('/orders', methods=['GET'])
def get_orders():
    """Get all orders"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute("""
            SELECT 
                o.id,
                o.customer_name as name,
                o.phone,
                o.amount,
                o.status,
                o.service,
                o.receipt,
                o.created_at,
                pi.payment_intent_id,
                c.conversation_id,
                c.current_state as conversation_state
            FROM orders o
            LEFT JOIN payment_intents pi ON o.id = pi.order_id
            LEFT JOIN conversations c ON pi.conversation_id = c.conversation_id
            ORDER BY o.created_at DESC
        """)
        
        orders = cursor.fetchall()
        conn.close()
        
        # Convert to list of dicts and format dates
        result = []
        for order in orders:
            order_dict = dict(order)
            if order_dict['created_at']:
                order_dict['created_at'] = order_dict['created_at'].isoformat()
            result.append(order_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"✗ Error fetching orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/conversations', methods=['GET'])
def get_conversations():
    """Get all conversations with stats"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute("""
            SELECT 
                c.conversation_id,
                c.customer_phone,
                c.customer_name,
                c.current_state,
                c.last_message_at,
                c.last_customer_message_at,
                c.follow_up_count,
                c.created_at,
                COUNT(DISTINCT o.id) as total_orders,
                COALESCE(SUM(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END), 0) as total_paid,
                COUNT(DISTINCT CASE WHEN ft.status = 'pending' THEN ft.task_id END) as pending_followups
            FROM conversations c
            LEFT JOIN payment_intents pi ON c.conversation_id = pi.conversation_id
            LEFT JOIN orders o ON pi.order_id = o.id
            LEFT JOIN follow_up_tasks ft ON c.conversation_id = ft.conversation_id
            GROUP BY c.conversation_id
            ORDER BY c.last_message_at DESC
        """)
        
        conversations = cursor.fetchall()
        conn.close()
        
        # Convert to list of dicts and format dates
        result = []
        for conv in conversations:
            conv_dict = dict(conv)
            if conv_dict['last_message_at']:
                conv_dict['last_message_at'] = conv_dict['last_message_at'].isoformat()
            if conv_dict['created_at']:
                conv_dict['created_at'] = conv_dict['created_at'].isoformat()
            if conv_dict['last_customer_message_at']:
                conv_dict['last_customer_message_at'] = conv_dict['last_customer_message_at'].isoformat()
            
            # Convert Decimal to float
            conv_dict['total_paid'] = float(conv_dict['total_paid'])
            
            result.append(conv_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"✗ Error fetching conversations: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/conversations/<conversation_id>/messages', methods=['GET'])
def get_conversation_messages(conversation_id):
    """Get all messages for a conversation"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute("""
            SELECT 
                message_id,
                direction,
                sender_phone,
                message_body,
                sent_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY sent_at ASC
        """, (conversation_id,))
        
        messages = cursor.fetchall()
        conn.close()
        
        # Format response
        result = []
        for msg in messages:
            msg_dict = dict(msg)
            msg_dict['sent_at'] = msg_dict['sent_at'].isoformat()
            result.append(msg_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"✗ Error fetching messages: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/orders/create', methods=['POST'])
def create_order():
    """Create new order (for manual entry or testing)"""
    try:
        data = request.get_json()
        
        customer_name = data.get('customer_name')
        phone = data.get('phone')
        amount = data.get('amount')
        service = data.get('service')
        
        # Get or create conversation
        conversation = get_or_create_conversation(phone)
        
        # Create payment intent
        payment_intent_id = create_payment_intent(
            conversation['conversation_id'],
            amount,
            service
        )
        
        # Create order
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute("""
            INSERT INTO orders (customer_name, phone, amount, service, status)
            VALUES (%s, %s, %s, %s, 'PENDING')
            RETURNING id
        """, (customer_name, phone, amount, service))
        
        order_id = cursor.fetchone()['id']
        
        # Link order to payment intent
        cursor.execute("""
            UPDATE payment_intents
            SET order_id = %s
            WHERE payment_intent_id = %s
        """, (order_id, payment_intent_id))
        
        conn.commit()
        conn.close()
        
        # Initiate STK push
        checkout_id = initiate_stk_push(
            phone,
            amount,
            f"Order-{order_id}",
            payment_intent_id
        )
        
        if checkout_id:
            return jsonify({
                "success": True,
                "order_id": order_id,
                "payment_intent_id": str(payment_intent_id),
                "checkout_request_id": checkout_id
            }), 201
        else:
            return jsonify({
                "success": False,
                "error": "Failed to initiate payment"
            }), 500
        
    except Exception as e:
        print(f"✗ Error creating order: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
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
