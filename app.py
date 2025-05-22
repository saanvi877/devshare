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
    <html>
        <head><title>Screenshot Manager Bot Service</title></head>
        <body>
            <h1>Screenshot Manager Bot Service</h1>
            <p>This is the server for the Screenshot Manager application.</p>
            <p>Active users: {}</p>
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
                    "Welcome to Screenshot Manager! To use this bot, please register with the desktop application."
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
                send_telegram_message(chat_id, "Screenshot received and ready for your desktop app.")
                
                return jsonify({"status": "success", "message": "Photo received"})
            
            # Handle text commands
            if 'text' in message:
                text = message['text']
                
                # Handle /start command
                if text.startswith('/start'):
                    instructions = (
                        "Welcome to Screenshot Manager!\n\n"
                        "To use this bot:\n"
                        "1. Open the Screenshot Manager desktop app\n"
                        "2. Enter your Telegram ID: {}\n"
                        "3. Connect to the service\n"
                        "4. Send screenshots from your phone\n\n"
                        "They will automatically appear on your desktop."
                    ).format(user_id)
                    
                    send_telegram_message(chat_id, instructions)
                    return jsonify({"status": "success", "message": "Instructions sent"})
                
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

def send_telegram_message(chat_id, text):
    """Helper function to send a message via Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    response = requests.post(url, json=payload)
    return response.json()

if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Run the app
    app.run(host='0.0.0.0', port=port) 
