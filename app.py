from flask import Flask, request, jsonify, Response, stream_with_context
import os
import requests
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import uuid
import base64
from flask_caching import Cache
import threading
import time
import gc
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Add file handler separately to avoid issues
logger = logging.getLogger(__name__)
try:
    file_handler = RotatingFileHandler('server.log', maxBytes=1024*1024, backupCount=3)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
except Exception as e:
    print(f"Warning: Could not set up log file: {e}")

app = Flask(__name__)

# Configure cache - use small memory limits
cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 3600,
    "CACHE_THRESHOLD": 100  # Limit number of items in cache
}
app.config.from_mapping(cache_config)
cache = Cache(app)

# Server configuration
CONFIG = {
    "max_users": 100,  # Maximum number of users to track
    "max_screenshots_per_user": 10000,  # Maximum screenshots per user
    "cleanup_interval_seconds": 600,  # How often to clean up inactive users (increased to 10 minutes)
    "inactive_timeout_minutes": 1000,  # When to consider a user inactive (increased to 60 minutes)
    "send_confirmations": True,  # Whether to send confirmation messages
    "max_screenshot_size_bytes": 1024 * 1024 * 10,  # 10MB max screenshot size
    "memory_check_interval": 60,  # Check memory usage every minute
    "start_time": datetime.now().isoformat(),  # Track when server started
    "connection_retry_count": 3,  # Number of retry attempts for failed connections
}

# In-memory database of registered users (in production, use a real database)
registered_users = {}

# Bot token from environment variable
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set")
    raise ValueError("BOT_TOKEN environment variable is required")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Store pending screenshots for clients to pull
pending_screenshots = {}

# Track memory usage
def get_memory_usage():
    """Get approximate memory usage of the process in MB"""
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # Convert to MB
    except ImportError:
        return 0  # If psutil not available

# Background task to clean inactive users and manage memory
def cleanup_and_monitor():
    while True:
        try:
            # Memory check and cleanup
            memory_mb = get_memory_usage()
            
            if memory_mb > 400:  # If using more than 400MB (out of 512MB)
                logger.warning(f"High memory usage: {memory_mb:.2f}MB - forcing garbage collection")
                # Force garbage collection
                gc.collect()
                
                # More aggressive cleanup if needed
                if memory_mb > 450:  # Critical memory pressure
                    logger.warning("Critical memory pressure - clearing caches")
                    # Clear cache
                    cache.clear()
                    
                    # Reduce stored screenshots
                    for conn_id in pending_screenshots:
                        # Keep only the most recent screenshot if multiple exist
                        if len(pending_screenshots[conn_id]) > 1:
                            pending_screenshots[conn_id] = pending_screenshots[conn_id][-1:]
            
            # Regular user cleanup - only for truly inactive users
            current_time = datetime.now()
            inactive_timeout = timedelta(minutes=CONFIG["inactive_timeout_minutes"])
            
            # Create a copy of the keys to prevent modification during iteration
            user_ids = list(registered_users.keys())
            
            # Find inactive users
            inactive_users = []
            for user_id in user_ids:
                # Skip if user no longer exists (might have been removed by another process)
                if user_id not in registered_users:
                    continue
                    
                try:
                    user_data = registered_users[user_id]
                    last_ping = datetime.fromisoformat(user_data['last_ping'])
                    
                    # Only mark as inactive if truly long time without ping
                    if current_time - last_ping > inactive_timeout:
                        inactive_users.append(user_id)
                except (ValueError, KeyError) as e:
                    logger.error(f"Error parsing last_ping for user {user_id}: {e}")
                    # If we can't parse last_ping, don't remove the user
                    continue
                    
            # Remove inactive users
            for user_id in inactive_users:
                # Check again if user still exists
                if user_id not in registered_users:
                    continue
                    
                connection_id = registered_users[user_id]['connection_id']
                logger.info(f"Removing inactive user {user_id}")
                
                # Clean up pending screenshots
                if connection_id in pending_screenshots:
                    del pending_screenshots[connection_id]
                    
                # Remove user
                del registered_users[user_id]
            
            # Log active users periodically
            if random.random() < 0.1:  # ~10% chance to log stats
                logger.debug(f"Active users: {len(registered_users)}, Connections: {len(pending_screenshots)}")
                logger.debug(f"Registered users: {list(registered_users.keys())}")
            
            # Sleep interval (longer to reduce CPU usage)
            time.sleep(CONFIG["cleanup_interval_seconds"])
            
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            time.sleep(CONFIG["cleanup_interval_seconds"])

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_and_monitor, daemon=True)
cleanup_thread.start()

@app.route('/')
def home():
    """Home page with comprehensive info and usage instructions"""
    active_users = len(registered_users)
    memory_usage = f"{get_memory_usage():.2f} MB" if get_memory_usage() > 0 else "Unknown"
    
    return f"""
    <html>
        <head>
            <title>DevShare - Screenshot Manager Bot</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                }}
                h1 {{
                    color: #2c3e50;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #3498db;
                    margin-top: 20px;
                }}
                .stats {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                code {{
                    background-color: #f5f5f5;
                    padding: 2px 5px;
                    border-radius: 3px;
                    font-family: monospace;
                }}
                ul {{
                    margin-left: 20px;
                }}
                .steps {{
                    margin-left: 0;
                    padding-left: 0;
                    list-style-type: none;
                }}
                .steps li {{
                    margin-bottom: 10px;
                    padding-left: 30px;
                    position: relative;
                }}
                .steps li:before {{
                    content: attr(data-step);
                    position: absolute;
                    left: 0;
                    top: 0;
                    background-color: #3498db;
                    color: white;
                    width: 20px;
                    height: 20px;
                    border-radius: 50%;
                    text-align: center;
                    line-height: 20px;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <h1>DevShare - Screenshot Manager Bot</h1>
            
            <div class="stats">
                <p><strong>Server Status:</strong> Online</p>
                <p><strong>Active Users:</strong> {active_users}</p>
                <p><strong>Memory Usage:</strong> {memory_usage}</p>
            </div>
            
            <h2>What is DevShare?</h2>
            <p>DevShare is a productivity tool that seamlessly transfers screenshots from your phone to your computer with zero friction. 
            It automatically copies received screenshots to your clipboard, making them instantly available for pasting in any application.</p>
            
            <h2>Getting Started</h2>
            <ol class="steps">
                <li data-step="1">Find your Telegram ID by messaging <a href="https://t.me/userinfobot">@userinfobot</a> on Telegram</li>
                <li data-step="2">Install the DevShare desktop application from <a href="https://github.com/Rkcr7/DevShare">GitHub</a></li>
                <li data-step="3">During setup, enter your Telegram ID when prompted</li>
                <li data-step="4">Connect to the Telegram bot: <a href="https://t.me/Screenshot_rk7_bot">@Screenshot_rk7_bot</a></li>
                <li data-step="5">Send screenshots from your phone to the bot</li>
                <li data-step="6">They appear instantly on your desktop, ready to paste!</li>
            </ol>
            
            <h2>Key Features</h2>
            <ul>
                <li>Instant phone-to-PC screenshot transfer</li>
                <li>Automatic clipboard integration</li>
                <li>Screenshot history management</li>
                <li>Cross-platform (Windows, macOS, Linux)</li>
                <li>Secure, authenticated connections</li>
            </ul>
            
            <h2>Use Cases</h2>
            <ul>
                <li><strong>Web & Mobile Development:</strong> Share mobile app screenshots instantly with your team</li>
                <li><strong>AI & Development:</strong> Capture phone content and paste directly into Cursor.sh or other AI tools</li> 
                <li><strong>Design Reviews:</strong> Share visual feedback without interrupting workflow</li>
                <li><strong>Remote Troubleshooting:</strong> Help others with tech issues by receiving their screenshots instantly</li>
            </ul>
            
            <h2>Recent Updates</h2>
            <ul>
                <li>Improved memory management for resource-constrained environments</li>
                <li>Added configurable notification settings</li>
                <li>Enhanced error handling and logging</li>
                <li>Optimized memory usage for screenshot storage</li>
            </ul>
            
            <h2>Need Help?</h2>
            <p>For support, report issues on <a href="https://github.com/Rkcr7/DevShare/issues">GitHub Issues</a> 
            or contact the developer at <a href="mailto:ritik135001@gmail.com">ritik135001@gmail.com</a></p>
        </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram webhook callbacks"""
    data = request.json
    logger.info(f"Received webhook: {data}")
    
    try:
        # Extract message data
        if 'message' in data:
            message = data['message']
            chat_id = message['chat']['id']
            user_id = str(message['from']['id'])
            
            # Check if this is a new user or first message
            if user_id not in registered_users:
                # Send welcome message with instructions
                send_telegram_message(
                    chat_id,
                    "Welcome to DevShare! To use this bot, please register with the desktop application."
                )
                return jsonify({"status": "success", "message": "Welcome message sent"})
            
            # Handle photo messages
            if 'photo' in message:
                logger.info(f"Received photo from user {user_id}")
                
                # Get the largest photo (best quality)
                photo = message['photo'][-1]
                file_id = photo['file_id']
                
                # Get file info
                file_info = get_file_info(file_id)
                if not file_info or 'file_path' not in file_info:
                    return jsonify({"status": "error", "message": "Could not get file info"})
                
                file_path = file_info['file_path']
                
                # Download file
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                photo_content = download_file(file_url)
                
                # Check file size
                if len(photo_content) > CONFIG["max_screenshot_size_bytes"]:
                    send_telegram_message(chat_id, "⚠️ Screenshot is too large. Please send a smaller image.")
                    return jsonify({"status": "error", "message": "Screenshot too large"})
                
                # Store for client to pull
                connection_id = registered_users[user_id]['connection_id']
                if connection_id not in pending_screenshots:
                    pending_screenshots[connection_id] = []
                
                # Enforce the maximum screenshots per user
                if len(pending_screenshots[connection_id]) >= CONFIG["max_screenshots_per_user"]:
                    # Remove oldest screenshots to make room
                    pending_screenshots[connection_id] = pending_screenshots[connection_id][-(CONFIG["max_screenshots_per_user"]-1):]
                
                # Add photo data and timestamp
                timestamp = datetime.now().isoformat()
                pending_screenshots[connection_id].append({
                    'data': photo_content,
                    'timestamp': timestamp,
                    'file_type': file_path.split('.')[-1]  # Get file extension
                })
                
                # Confirm to user if confirmations are enabled
                if CONFIG["send_confirmations"]:
                    # Check if user has desktop connected
                    if user_id in registered_users and registered_users[user_id]['active']:
                        send_telegram_message(chat_id, "✅ Screenshot received → your desktop")
                    else:
                        send_telegram_message(chat_id, "⚠️ Screenshot received, but your desktop app appears to be offline.")
                
                return jsonify({"status": "success", "message": "Photo received"})
            
            # Handle text commands
            if 'text' in message:
                text = message['text']
                
                # Handle /start command
                if text.startswith('/start'):
                    instructions = (
                        "Welcome to DevShare!\n\n"
                        "With DevShare, you can instantly transfer screenshots from your phone to your PC.\n\n"
                        "To use this bot:\n"
                        "1. Open the DevShare desktop app\n"
                        "2. Enter your Telegram ID: {}\n"
                        "3. Connect to the service\n"
                        "4. Send screenshots from your phone\n\n"
                        "They will automatically appear on your desktop and be copied to your clipboard for instant pasting anywhere.\n\n"
                        "Learn more at: https://github.com/Rkcr7/DevShare"
                    ).format(user_id)
                    
                    send_telegram_message(chat_id, instructions)
                    return jsonify({"status": "success", "message": "Instructions sent"})
                
                # Handle /help command
                if text.startswith('/help'):
                    help_text = (
                        "DevShare Help:\n\n"
                        "• Just send any screenshot to this bot\n"
                        "• Make sure your desktop app is running\n"
                        "• Screenshots are automatically copied to your clipboard\n"
                        "• View your screenshot history in the desktop app\n\n"
                        "Commands:\n"
                        "/start - Get started with DevShare\n"
                        "/help - Show this help message\n"
                        "/status - Check connection status\n"
                        "/silent - Toggle notification messages\n\n"
                        "Need more help? Visit https://github.com/Rkcr7/DevShare"
                    )
                    send_telegram_message(chat_id, help_text)
                    return jsonify({"status": "success", "message": "Help sent"})
                
                # Handle /status command
                if text.startswith('/status'):
                    if user_id in registered_users and registered_users[user_id]['active']:
                        status_text = "✅ Your DevShare connection is active and working properly."
                    else:
                        status_text = "❌ Your DevShare desktop app is not currently connected.\n\nPlease start the app on your computer."
                    
                    send_telegram_message(chat_id, status_text)
                    return jsonify({"status": "success", "message": "Status sent"})
                
                # Handle /silent command to toggle notifications
                if text.startswith('/silent'):
                    CONFIG["send_confirmations"] = not CONFIG["send_confirmations"]
                    if CONFIG["send_confirmations"]:
                        send_telegram_message(chat_id, "🔊 Notifications enabled - you'll receive confirmation when screenshots are sent.")
                    else:
                        send_telegram_message(chat_id, "🔇 Silent mode enabled - no more screenshot confirmations.")
                    
                    return jsonify({"status": "success", "message": "Notification setting updated"})
                
                # Handle other commands or messages
                send_telegram_message(chat_id, "Send me screenshots to transfer them to your desktop.")
                return jsonify({"status": "success", "message": "Default response sent"})
    
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})
    
    return jsonify({"status": "success"})

@app.route('/register', methods=['POST'])
def register():
    """Register a new desktop client"""
    try:
        data = request.json
        user_id = data.get('telegram_id')
        
        logger.info(f"Registration request received for user: {user_id}")
        
        if not user_id:
            logger.warning("Registration attempt without telegram_id")
            return jsonify({"status": "error", "message": "Missing telegram_id"})
        
        # Check if maximum users reached
        if len(registered_users) >= CONFIG["max_users"] and user_id not in registered_users:
            logger.warning(f"Maximum users reached, rejecting new user: {user_id}")
            return jsonify({
                "status": "error", 
                "message": "Server at capacity. Please try again later."
            })
        
        # Generate connection ID
        connection_id = str(uuid.uuid4())
        
        # Register the user
        registered_users[user_id] = {
            "connection_id": connection_id,
            "last_ping": datetime.now().isoformat(),
            "active": True
        }
        
        # Initialize pending screenshots queue
        pending_screenshots[connection_id] = []
        
        logger.info(f"Registered user {user_id} with connection {connection_id}")
        logger.debug(f"Current registered users: {list(registered_users.keys())}")
        logger.debug(f"User data: {registered_users[user_id]}")
        
        return jsonify({
            "status": "success", 
            "message": "Registration successful",
            "connection_id": connection_id
        })
        
    except Exception as e:
        logger.error(f"Error in registration: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/ping', methods=['POST'])
def ping():
    """Client ping to maintain connection and check for new screenshots"""
    try:
        data = request.json
        connection_id = data.get('connection_id')
        
        if not connection_id:
            return jsonify({"status": "error", "message": "Missing connection_id"})
        
        # Debug log for troubleshooting
        logger.info(f"Ping received for connection: {connection_id}")
        
        # Thread-safe copy of registered users
        active_users = dict(registered_users)
        
        # Find user by connection ID
        user_found = False
        for user_id, user_data in active_users.items():
            if user_data.get('connection_id') == connection_id:
                # Update user's last ping time
                registered_users[user_id]['last_ping'] = datetime.now().isoformat()
                registered_users[user_id]['active'] = True
                user_found = True
                logger.info(f"User found for connection {connection_id}: {user_id}")
                break
        
        if not user_found:
            # Double-check all connections more thoroughly to avoid race conditions
            connection_found = False
            for user_id, user_data in list(registered_users.items()):
                if user_data.get('connection_id') == connection_id:
                    connection_found = True
                    # The connection is valid but wasn't found in our first pass
                    # Update anyway to reconnect
                    registered_users[user_id]['last_ping'] = datetime.now().isoformat()
                    registered_users[user_id]['active'] = True
                    logger.info(f"Connection recovered for {connection_id}: {user_id}")
                    user_found = True
                    break
                    
            if not connection_found:
                logger.warning(f"Invalid connection ID in ping: {connection_id}")
                logger.debug(f"Current registered users: {list(registered_users.keys())}")
            
                # Attempt to re-register this connection if we have an ongoing session
                for user_id, user_data in list(registered_users.items()):
                    # Look for matching connection ID in pending_screenshots
                    if connection_id in pending_screenshots:
                        # Re-link the connection to this user
                        registered_users[user_id]['connection_id'] = connection_id
                        registered_users[user_id]['last_ping'] = datetime.now().isoformat()
                        registered_users[user_id]['active'] = True
                        logger.info(f"Re-linked connection {connection_id} to user {user_id}")
                        user_found = True
                        break
                    
                if not user_found:
                    return jsonify({"status": "error", "message": "Invalid connection_id"})
        
        # Check if there are pending screenshots
        has_pending = connection_id in pending_screenshots and len(pending_screenshots[connection_id]) > 0
        
        return jsonify({
            "status": "success",
            "has_pending_screenshots": has_pending
        })
        
    except Exception as e:
        logger.error(f"Error in ping: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/fetch', methods=['POST'])
def fetch_screenshots():
    """Fetch pending screenshots for a client"""
    try:
        data = request.json
        connection_id = data.get('connection_id')
        
        if not connection_id:
            return jsonify({"status": "error", "message": "Missing connection_id"})
        
        # Check if connection ID is valid
        if connection_id not in pending_screenshots:
            return jsonify({"status": "error", "message": "Invalid connection_id"})
        
        # Get pending screenshots
        screenshots = pending_screenshots[connection_id]
        
        # Clear the queue after sending
        pending_screenshots[connection_id] = []
        
        # For very large responses, use streaming to reduce memory usage
        if len(screenshots) > 3:  # If more than 3 screenshots
            def generate():
                yield '{"status": "success", "screenshots": ['
                
                for i, screenshot in enumerate(screenshots):
                    # Check if data is already bytes
                    if isinstance(screenshot['data'], bytes):
                        encoded_data = base64.b64encode(screenshot['data']).decode('utf-8')
                    else:
                        encoded_data = screenshot['data']
                    
                    screenshot_json = json.dumps({
                        'data': encoded_data,
                        'timestamp': screenshot['timestamp'],
                        'file_type': screenshot.get('file_type', 'png')
                    })
                    
                    if i < len(screenshots) - 1:
                        yield screenshot_json + ','
                    else:
                        yield screenshot_json
                
                yield ']}'
            
            return Response(stream_with_context(generate()), mimetype='application/json')
        else:
            # For smaller responses, use regular approach
            encoded_screenshots = []
            for screenshot in screenshots:
                # Check if data is already bytes
                if isinstance(screenshot['data'], bytes):
                    encoded_data = base64.b64encode(screenshot['data']).decode('utf-8')
                else:
                    encoded_data = screenshot['data']
                    
                encoded_screenshots.append({
                    'data': encoded_data,
                    'timestamp': screenshot['timestamp'],
                    'file_type': screenshot.get('file_type', 'png')
                })
            
            return jsonify({
                "status": "success",
                "screenshots": encoded_screenshots
            })
        
    except Exception as e:
        logger.error(f"Error fetching screenshots: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

# Add caching for API calls and file downloads
@cache.memoize(timeout=3600)
def get_file_info(file_id):
    """Get file info with caching"""
    file_path_response = requests.get(f"{TELEGRAM_API}/getFile?file_id={file_id}")
    file_info = file_path_response.json().get('result', {})
    return file_info

@cache.memoize(timeout=3600)
def download_file(url):
    """Download file with caching"""
    response = requests.get(url)
    return response.content

def send_telegram_message(chat_id, text):
    """Helper function to send a message via Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    response = requests.post(url, json=payload)
    return response.json()

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    memory_usage = get_memory_usage()
    return jsonify({
        "status": "healthy",
        "version": "1.2.0",
        "active_users": len(registered_users),
        "pending_screenshots": sum(len(queue) for queue in pending_screenshots.values()),
        "memory_usage_mb": f"{memory_usage:.2f}" if memory_usage > 0 else "Unknown"
    })

# Simple API to change configuration
@app.route('/config', methods=['POST'])
def update_config():
    """Update server configuration - requires API key"""
    try:
        # Very simple security - should be improved in production
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != os.environ.get('API_KEY'):
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"})
        
        # Update configuration values
        for key, value in data.items():
            if key in CONFIG:
                CONFIG[key] = value
        
        return jsonify({
            "status": "success",
            "message": "Configuration updated",
            "config": CONFIG
        })
    
    except Exception as e:
        logger.error(f"Error updating configuration: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

# Static file served from cache
@app.route('/robots.txt')
def robots():
    """Serve robots.txt to avoid repeated requests"""
    content = "User-agent: *\nDisallow: /webhook\nDisallow: /register\nDisallow: /ping\nDisallow: /fetch"
    return Response(content, mimetype='text/plain')

# Debug endpoint to check server state - only available if DEBUG is enabled
@app.route('/debug', methods=['GET'])
def debug_state():
    """Debug endpoint to verify server state - only works if API_KEY is set"""
    # Security check
    api_key = request.args.get('key')
    if not api_key or api_key != os.environ.get('API_KEY'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    # Safe representation of registered_users (no sensitive data)
    safe_users = {}
    for user_id, data in registered_users.items():
        safe_users[user_id] = {
            "active": data.get("active", False),
            "last_ping": data.get("last_ping", "unknown"),
            "connection_id": data.get("connection_id", "none")
        }
    
    # Connection summary
    connections = {}
    for conn_id in pending_screenshots:
        connections[conn_id] = {
            "pending_screenshots": len(pending_screenshots[conn_id])
        }
    
    return jsonify({
        "status": "success",
        "server_info": {
            "version": "1.2.0",
            "memory_usage_mb": f"{get_memory_usage():.2f}" if get_memory_usage() > 0 else "Unknown",
            "start_time": CONFIG.get("start_time", "unknown"),
            "registered_users_count": len(registered_users),
            "pending_screenshots_count": sum(len(queue) for queue in pending_screenshots.values())
        },
        "registered_users": safe_users,
        "connections": connections,
        "config": {k: v for k, v in CONFIG.items() if k != "api_key"}
    })

if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Run the app
    app.run(host='0.0.0.0', port=port) 
