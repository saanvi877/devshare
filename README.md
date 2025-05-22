# Screenshot Manager Bot Server

A centralized server for the Screenshot Manager application that handles communication with the Telegram bot and distributes screenshots to connected clients.

## Architecture

The server has the following components:

1. **Flask Web Server**: Handles HTTP requests from both Telegram and desktop clients
2. **Webhook Handler**: Processes incoming Telegram messages containing screenshots
3. **Client API**: Allows desktop applications to register and fetch screenshots
4. **In-memory Database**: Stores pending screenshots and client information

## Deployment on Heroku

### Prerequisites

- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
- [Git](https://git-scm.com/)
- A Telegram Bot token (from [@BotFather](https://t.me/botfather))
- A verified Heroku account (requires adding payment information)

### Option 1: Using the Deployment Script

1. Make sure you have the Heroku CLI installed and are logged in
2. In the `server` directory, run:
   ```
   python deploy.py
   ```
3. Follow the prompts to enter your application name and bot token
4. The script will handle deployment and webhook setup automatically

### Option 2: Manual Deployment

1. Install the Heroku CLI and login:
   ```
   heroku login
   ```

2. Create a new Heroku app:
   ```
   heroku create your-app-name
   ```

3. Set your Telegram bot token as an environment variable:
   ```
   heroku config:set BOT_TOKEN=your_bot_token_here --app your-app-name
   ```

4. Initialize a Git repository in the server directory if not already done:
   ```
   git init
   ```

5. Add the Heroku remote:
   ```
   heroku git:remote -a your-app-name
   ```

6. Commit and push to Heroku:
   ```
   git add .
   git commit -m "Initial deployment"
   git push heroku main
   ```

7. Set up the Webhook URL for your Telegram bot:
   ```
   curl "https://api.telegram.org/botyour_bot_token/setWebhook?url=https://your-app-name.herokuapp.com/webhook"
   ```

## Alternative Deployment: Railway

Railway is a platform that offers a simpler deployment experience and includes a free tier without requiring payment verification.

### Prerequisites

- [GitHub account](https://github.com)
- Railway account (can sign up with GitHub)
- A Telegram Bot token (from [@BotFather](https://t.me/botfather))

### Deployment Steps

1. Go to [Railway](https://railway.app/) and sign up/log in with your GitHub account

2. Create a new project and select "Deploy from GitHub repo"

3. Connect your GitHub account and select your Screenshot Manager Bot repository

4. Configure environment variables:
   - Add `BOT_TOKEN` with your Telegram bot token value

5. After deployment, get your app's URL from the "Settings" tab

6. Set up your Telegram bot webhook with:
   ```
   curl "https://api.telegram.org/botyour_bot_token/setWebhook?url=https://your-railway-url.up.railway.app/webhook"
   ```

## Local Development

1. Create a `.env` file in the server directory with:
   ```
   BOT_TOKEN=your_bot_token_here
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the Flask app:
   ```
   python app.py
   ```

4. For testing with Telegram while running locally, you'll need a service like ngrok:
   ```
   ngrok http 5000
   ```
   
   Then set your webhook to the ngrok URL:
   ```
   curl "https://api.telegram.org/botyour_bot_token/setWebhook?url=https://your-ngrok-url.ngrok.io/webhook"
   ```

## Client Connection

Desktop clients should connect to the following endpoints:

- `/register` - Register a new client with the service
- `/ping` - Check for new screenshots
- `/fetch` - Download pending screenshots

See the client code in `modules/cloud_service.py` for implementation details.

## License

MIT License