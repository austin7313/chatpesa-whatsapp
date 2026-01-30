"""
DIAGNOSTIC VERSION - FlowStack Troubleshooting Backend
This version has extensive logging and diagnostics to identify issues
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import sys
from datetime import datetime
import traceback

# ============================================================================
# DIAGNOSTIC PRINTS
# ============================================================================

print("=" * 80)
print("🔍 FLOWSTACK DIAGNOSTIC MODE")
print("=" * 80)
print(f"Python version: {sys.version}")
print(f"Starting at: {datetime.now()}")
print("")

# ============================================================================
# FLASK APP SETUP
# ============================================================================

app = Flask(__name__)

# Enable CORS with verbose logging
print("📡 Configuring CORS...")
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})
print("✓ CORS enabled for all origins")
print("")

# ============================================================================
# ENVIRONMENT VARIABLES CHECK
# ============================================================================

print("🔐 Checking Environment Variables:")
print("-" * 80)

required_vars = {
    'DATABASE_URL': 'PostgreSQL connection string',
    'TWILIO_ACCOUNT_SID': 'Twilio Account SID (optional for basic testing)',
    'TWILIO_AUTH_TOKEN': 'Twilio Auth Token (optional for basic testing)',
    'TWILIO_WHATSAPP_NUMBER': 'Twilio WhatsApp number (optional for basic testing)'
}

env_status = {}
for var, description in required_vars.items():
    value = os.environ.get(var)
    env_status[var] = value is not None
    
    if value:
        # Mask sensitive values
        if 'TOKEN' in var or 'SECRET' in var or 'PASSWORD' in var:
            display_value = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
        elif 'URL' in var:
            display_value = value[:20] + "..." if len(value) > 20 else value
        else:
            display_value = value[:30] + "..." if len(value) > 30 else value
        
        print(f"✓ {var}: {display_value}")
    else:
        print(f"✗ {var}: MISSING ({description})")

print("")

# Store variables
DATABASE_URL = os.environ.get('DATABASE_URL')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')

# ============================================================================
# DATABASE CONNECTION TEST
# ============================================================================

print("🗄️  Testing Database Connection:")
print("-" * 80)

db_connection_ok = False
db_error = None

def test_database():
    """Test database connection and return diagnostics"""
    global db_connection_ok, db_error
    
    if not DATABASE_URL:
        db_error = "DATABASE_URL not set in environment variables"
        print(f"✗ {db_error}")
        return False
    
    try:
        print(f"Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT NOW(), version()")
        result = cursor.fetchone()
        
        print(f"✓ Database connection successful!")
        print(f"  Server time: {result[0]}")
        print(f"  PostgreSQL version: {result[1][:50]}...")
        
        # Check if orders table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'orders'
            )
        """)
        orders_exists = cursor.fetchone()[0]
        
        if orders_exists:
            cursor.execute("SELECT COUNT(*) FROM orders")
            count = cursor.fetchone()[0]
            print(f"✓ 'orders' table found ({count} records)")
        else:
            print(f"⚠️  'orders' table NOT FOUND - needs to be created")
        
        # Check if conversations table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'conversations'
            )
        """)
        conversations_exists = cursor.fetchone()[0]
        
        if conversations_exists:
            cursor.execute("SELECT COUNT(*) FROM conversations")
            count = cursor.fetchone()[0]
            print(f"✓ 'conversations' table found ({count} records)")
        else:
            print(f"⚠️  'conversations' table NOT FOUND - using basic mode")
        
        conn.close()
        db_connection_ok = True
        return True
        
    except psycopg2.OperationalError as e:
        db_error = f"Database connection failed: {str(e)}"
        print(f"✗ {db_error}")
        return False
    except Exception as e:
        db_error = f"Database error: {str(e)}"
        print(f"✗ {db_error}")
        traceback.print_exc()
        return False

# Run database test
test_database()
print("")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db_connection():
    """Get database connection with error handling"""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not configured")
    return psycopg2.connect(DATABASE_URL)

# ============================================================================
# DIAGNOSTIC ENDPOINTS
# ============================================================================

@app.route('/', methods=['GET'])
def root():
    """Root endpoint - diagnostic information"""
    return jsonify({
        "status": "online",
        "service": "FlowStack Backend (Diagnostic Mode)",
        "timestamp": datetime.now().isoformat(),
        "diagnostics": {
            "database_connected": db_connection_ok,
            "database_error": db_error,
            "environment_variables": env_status,
            "python_version": sys.version,
            "endpoints": [
                "GET /",
                "GET /health",
                "GET /diagnostics",
                "GET /test-db",
                "GET /test-cors",
                "GET /orders",
                "POST /webhook/whatsapp"
            ]
        }
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Simple health check"""
    return jsonify({
        "status": "online" if db_connection_ok else "degraded",
        "database": "connected" if db_connection_ok else "disconnected",
        "timestamp": datetime.now().isoformat()
    }), 200 if db_connection_ok else 503

@app.route('/diagnostics', methods=['GET'])
def diagnostics():
    """Detailed diagnostics endpoint"""
    
    diagnostics_data = {
        "server_time": datetime.now().isoformat(),
        "python_version": sys.version,
        "environment": {
            "DATABASE_URL": "Set" if DATABASE_URL else "Missing",
            "TWILIO_ACCOUNT_SID": "Set" if TWILIO_ACCOUNT_SID else "Missing",
            "TWILIO_AUTH_TOKEN": "Set" if TWILIO_AUTH_TOKEN else "Missing",
            "TWILIO_WHATSAPP_NUMBER": "Set" if TWILIO_WHATSAPP_NUMBER else "Missing",
        },
        "database": {
            "connected": db_connection_ok,
            "error": db_error
        }
    }
    
    # Try to get database info
    if db_connection_ok:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Get table info
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row['table_name'] for row in cursor.fetchall()]
            
            diagnostics_data["database"]["tables"] = tables
            
            # Get orders count if table exists
            if 'orders' in tables:
                cursor.execute("SELECT COUNT(*) as count FROM orders")
                diagnostics_data["database"]["orders_count"] = cursor.fetchone()['count']
            
            # Get conversations count if table exists
            if 'conversations' in tables:
                cursor.execute("SELECT COUNT(*) as count FROM conversations")
                diagnostics_data["database"]["conversations_count"] = cursor.fetchone()['count']
            
            conn.close()
            
        except Exception as e:
            diagnostics_data["database"]["query_error"] = str(e)
    
    return jsonify(diagnostics_data), 200

@app.route('/test-db', methods=['GET'])
def test_db():
    """Test database connection and return status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT NOW() as server_time, version() as version")
        result = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": "Database connection successful",
            "server_time": str(result[0]),
            "postgres_version": result[1]
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Database connection failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/test-cors', methods=['GET', 'POST', 'OPTIONS'])
def test_cors():
    """Test CORS configuration"""
    return jsonify({
        "status": "success",
        "message": "CORS is working",
        "method": request.method,
        "headers": dict(request.headers),
        "origin": request.headers.get('Origin', 'No origin header')
    }), 200

# ============================================================================
# BASIC ORDERS ENDPOINT (WITH EXTENSIVE LOGGING)
# ============================================================================

@app.route('/orders', methods=['GET'])
def get_orders():
    """Get all orders with detailed error logging"""
    
    print("\n" + "="*80)
    print(f"📊 /orders endpoint called at {datetime.now()}")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print("="*80)
    
    try:
        # Check database connection
        if not db_connection_ok:
            error_response = {
                "error": "Database not connected",
                "details": db_error,
                "help": "Check DATABASE_URL environment variable"
            }
            print(f"✗ Database not connected: {db_error}")
            return jsonify(error_response), 500
        
        # Connect to database
        print("Connecting to database...")
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("✓ Connected")
        
        # Check if orders table exists
        print("Checking if 'orders' table exists...")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'orders'
            )
        """)
        table_exists = cursor.fetchone()['exists']
        
        if not table_exists:
            print("✗ 'orders' table does not exist!")
            
            # Get list of existing tables
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            existing_tables = [row['table_name'] for row in cursor.fetchall()]
            
            conn.close()
            
            return jsonify({
                "error": "Table 'orders' does not exist",
                "existing_tables": existing_tables,
                "help": "You need to create the 'orders' table first. Run the SQL migration."
            }), 404
        
        print("✓ 'orders' table exists")
        
        # Get column names
        print("Getting column information...")
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'orders'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        column_names = [col['column_name'] for col in columns]
        print(f"✓ Columns found: {', '.join(column_names)}")
        
        # Fetch orders
        print("Fetching orders...")
        cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100")
        orders = cursor.fetchall()
        print(f"✓ Found {len(orders)} orders")
        
        conn.close()
        
        # Convert to JSON-serializable format
        result = []
        for order in orders:
            order_dict = dict(order)
            
            # Convert datetime to ISO string
            for key, value in order_dict.items():
                if isinstance(value, datetime):
                    order_dict[key] = value.isoformat()
            
            result.append(order_dict)
        
        print(f"✓ Returning {len(result)} orders")
        print("="*80 + "\n")
        
        return jsonify(result), 200
        
    except psycopg2.Error as e:
        error_msg = f"Database error: {str(e)}"
        print(f"✗ {error_msg}")
        traceback.print_exc()
        
        return jsonify({
            "error": "Database query failed",
            "details": str(e),
            "type": type(e).__name__
        }), 500
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"✗ {error_msg}")
        traceback.print_exc()
        
        return jsonify({
            "error": "Server error",
            "details": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }), 500

# ============================================================================
# SIMPLE TEST ENDPOINT
# ============================================================================

@app.route('/test', methods=['GET'])
def test():
    """Simple test endpoint that always works"""
    return jsonify({
        "status": "success",
        "message": "Backend is running!",
        "timestamp": datetime.now().isoformat(),
        "note": "If you see this, your backend is working"
    }), 200

# ============================================================================
# WHATSAPP WEBHOOK (BASIC VERSION)
# ============================================================================

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """WhatsApp webhook with logging"""
    
    print("\n" + "="*80)
    print(f"📱 WhatsApp webhook called at {datetime.now()}")
    print("="*80)
    
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        
        print(f"From: {from_number}")
        print(f"Message: {incoming_msg}")
        
        # Simple echo response
        from twilio.twiml.messaging_response import MessagingResponse
        resp = MessagingResponse()
        resp.message(f"✓ Received: {incoming_msg}")
        
        print("✓ Response sent")
        print("="*80 + "\n")
        
        return str(resp), 200
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        traceback.print_exc()
        print("="*80 + "\n")
        return "Error", 500

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "error": "Endpoint not found",
        "path": request.path,
        "method": request.method,
        "available_endpoints": [
            "GET /",
            "GET /health",
            "GET /diagnostics",
            "GET /test-db",
            "GET /test-cors",
            "GET /test",
            "GET /orders",
            "POST /webhook/whatsapp"
        ]
    }), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "error": "Internal server error",
        "details": str(e),
        "help": "Check server logs for more details"
    }), 500

# ============================================================================
# STARTUP SUMMARY
# ============================================================================

print("🚀 Flask App Configuration Complete")
print("=" * 80)
print("Available Routes:")
print("  GET  /              - Diagnostic info")
print("  GET  /health        - Health check")
print("  GET  /diagnostics   - Detailed diagnostics")
print("  GET  /test-db       - Test database connection")
print("  GET  /test-cors     - Test CORS configuration")
print("  GET  /test          - Simple test endpoint")
print("  GET  /orders        - Get all orders (with logging)")
print("  POST /webhook/whatsapp - WhatsApp webhook")
print("=" * 80)
print("")

if db_connection_ok:
    print("✓ Database: CONNECTED")
else:
    print("✗ Database: DISCONNECTED")
    if db_error:
        print(f"  Error: {db_error}")

print("")
print("📍 Frontend URL to test:")
print("   Open browser: https://your-app.onrender.com/")
print("   Or test API:  https://your-app.onrender.com/test")
print("")
print("=" * 80)

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Starting server on port {port}...")
    print("=" * 80)
    print("")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True  # Enable debug mode for more detailed errors
    )
