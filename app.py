from flask import Flask, request, jsonify
import os
import requests
import json
import logging
from datetime import datetime
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory database of registered users (in production, use a real database)
# Structure: {telegram_id: {connection_id: str, last_ping: datetime, active: bool}}
registered_users = {}

# Bot token from environment variable
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set")
    raise ValueError("BOT_TOKEN environment variable is required")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Store pending screenshots for clients to pull
# Structure: {connection_id: [screenshot_data]}
pending_screenshots = {}

@app.route('/')
def home():
    """Home page with basic info"""
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>DevShare Service</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                h1 {
                    color: #1E88E5;
                    border-bottom: 2px solid #eee;
                    padding-bottom: 10px;
                }
                h2 {
                    margin-top: 25px;
                    color: #333;
                }
                .container {
                    background: #f9f9f9;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                .steps {
                    background: #f0f7ff;
                    padding: 15px;
                    border-radius: 6px;
                    border-left: 4px solid #1E88E5;
                }
                .stats {
                    background: #eee;
                    padding: 10px;
                    border-radius: 4px;
                    display: inline-block;
                    margin-top: 20px;
                }
                code {
                    background: #eee;
                    padding: 2px 5px;
                    border-radius: 3px;
                }
            </style>
        </head>
        <body>
            <h1>DevShare Service</h1>
            <div class="container">
                <p>Welcome to the DevShare server! This service enables instant transfer of screenshots from your phone to your computer.</p>
                
                <h2>How It Works</h2>
                <div class="steps">
                    <ol>
                        <li><strong>Desktop Setup:</strong> Install and run the DevShare desktop application</li>
                        <li><strong>Connect:</strong> Enter your Telegram ID in the desktop app to connect your devices</li>
                        <li><strong>Mobile Usage:</strong> Send screenshots to <code>@Screenshot_rk7_bot</code> on Telegram</li>
                        <li><strong>Instant Transfer:</strong> Screenshots appear instantly on your desktop's clipboard</li>
                    </ol>
                </div>
                
                <h2>Bot Commands</h2>
                <ul>
                    <li><code>/start</code> - View welcome message and instructions</li>
                    <li><code>/help</code> - Get usage help and troubleshooting tips</li>
                    <li><code>/status</code> - Check your connection status</li>
                </ul>
                
                <p>For detailed instructions, visit the <a href="https://github.com/Rkcr7/DevShare">DevShare GitHub repository</a>.</p>
                
                <div class="stats">
                    <p><strong>Active Users:</strong> {}</p>
                </div>
            </div>
        </body>
    </html>
    """.format(len(registered_users))

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
                    "👋 Welcome to DevShare! To use this bot, please connect with the desktop application first."
                )
                return jsonify({"status": "success", "message": "Welcome message sent"})
            
            # Handle photo messages
            if 'photo' in message:
                logger.info(f"Received photo from user {user_id}")
                
                # Get the largest photo (best quality)
                photo = message['photo'][-1]
                file_id = photo['file_id']
                
                # Get file path
                file_path_response = requests.get(f"{TELEGRAM_API}/getFile?file_id={file_id}")
                file_path = file_path_response.json()['result']['file_path']
                
                # Download file
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                photo_content = requests.get(file_url).content
                
                # Store for client to pull
                connection_id = registered_users[user_id]['connection_id']
                if connection_id not in pending_screenshots:
                    pending_screenshots[connection_id] = []
                
                # Add photo data and timestamp
                timestamp = datetime.now().isoformat()
                pending_screenshots[connection_id].append({
                    'data': photo_content,
                    'timestamp': timestamp,
                    'file_type': file_path.split('.')[-1]  # Get file extension
                })
                
                # Confirm to user
                send_telegram_message(
                    chat_id, 
                    "✅ Screenshot received! It's now available on your desktop.\n\nJust paste (Ctrl+V or Cmd+V) anywhere to use it."
                )
                
                return jsonify({"status": "success", "message": "Photo received"})
            
            # Handle text commands
            if 'text' in message:
                text = message['text']
                
                # Handle /start command
                if text.startswith('/start'):
                    instructions = (
                        "🚀 Welcome to DevShare!\n\n"
                        "📱 → 💻 Transfer screenshots instantly from phone to PC\n\n"
                        "📋 How to use:\n"
                        "1. Open the DevShare desktop app\n"
                        "2. Enter your Telegram ID: {}\n"
                        "3. Click 'Save and Continue'\n"
                        "4. Send screenshots from your phone to this chat\n\n"
                        "That's it! Screenshots will be automatically copied to your desktop clipboard."
                    ).format(user_id)
                    
                    send_telegram_message(chat_id, instructions)
                    return jsonify({"status": "success", "message": "Instructions sent"})
                
                # Handle /help command
                elif text.startswith('/help'):
                    help_text = (
                        "📋 DevShare Help\n\n"
                        "• Make sure the desktop app is running\n"
                        "• Send any screenshot to this chat\n"
                        "• Images are instantly copied to your PC clipboard\n"
                        "• Just paste anywhere (Ctrl+V or Cmd+V)\n\n"
                        "⚠️ Troubleshooting:\n"
                        "• Check your internet connection\n"
                        "• Restart the desktop app if needed\n"
                        "• Verify your Telegram ID is correct\n\n"
                        "For more help, visit: github.com/Rkcr7/DevShare"
                    )
                    send_telegram_message(chat_id, help_text)
                    return jsonify({"status": "success", "message": "Help sent"})
                
                # Handle /status command
                elif text.startswith('/status'):
                    # Find user connection info
                    user_data = registered_users.get(user_id, {})
                    if user_data and user_data.get('active', False):
                        status_text = (
                            "✅ You're connected to DevShare!\n\n"
                            "Your desktop app is actively receiving screenshots.\n"
                            "Last activity: {}"
                        ).format(user_data.get('last_ping', 'Unknown'))
                    else:
                        status_text = (
                            "❌ Not connected to desktop app\n\n"
                            "Please make sure the DevShare app is running on your computer."
                        )
                    
                    send_telegram_message(chat_id, status_text)
                    return jsonify({"status": "success", "message": "Status sent"})
                
                # Handle other messages
                else:
                    send_telegram_message(
                        chat_id, 
                        "📸 Send me screenshots to transfer them to your desktop.\n\nType /help for assistance."
                    )
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
        
        if not user_id:
            return jsonify({"status": "error", "message": "Missing telegram_id"})
        
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
        
        # Find user by connection ID
        user_found = False
        for user_id, user_data in registered_users.items():
            if user_data.get('connection_id') == connection_id:
                user_data['last_ping'] = datetime.now().isoformat()
                user_data['active'] = True
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
        
        # Return base64 encoded screenshot data
        import base64
        encoded_screenshots = []
        for screenshot in screenshots:
            encoded_screenshots.append({
                'data': base64.b64encode(screenshot['data']).decode('utf-8'),
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

@app.route('/set_commands', methods=['GET'])
def set_commands():
    """Set bot commands in Telegram"""
    try:
        commands = [
            {"command": "start", "description": "Start the bot and view welcome message"},
            {"command": "help", "description": "Get usage help and troubleshooting tips"},
            {"command": "status", "description": "Check connection status with desktop"}
        ]
        
        url = f"{TELEGRAM_API}/setMyCommands"
        response = requests.post(url, json={"commands": commands})
        
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Bot commands updated"})
        else:
            return jsonify({"status": "error", "message": f"Failed to update commands: {response.text}"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def send_telegram_message(chat_id, text):
    """Helper function to send a message via Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'  # Enable HTML formatting
    }
    response = requests.post(url, json=payload)
    return response.json()

if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Initialize bot commands on startup
    try:
        set_commands()
        logger.info("Bot commands initialized")
    except Exception as e:
        logger.error(f"Failed to initialize bot commands: {str(e)}")
    
    # Run the app
    app.run(host='0.0.0.0', port=port)
