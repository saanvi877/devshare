#!/usr/bin/env python
import os
import subprocess
import sys
import webbrowser
import requests
import json
import time

def run_command(command, silent=False):
    """Run a shell command and return its output and success status"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=False,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        
        if not silent:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(f"ERROR: {result.stderr}")
                
        return result.stdout, result.returncode == 0
    except Exception as e:
        if not silent:
            print(f"ERROR: {str(e)}")
        return "", False

def print_header(message):
    """Print a formatted header message"""
    print(f"\n>>> {message}")

def check_git():
    """Check if git is installed"""
    print_header("Checking if Git is installed")
    print("$ git --version")
    output, success = run_command("git --version")
    
    if not success or "git version" not in output.lower():
        print("Git not found! Please install Git from: https://git-scm.com/downloads")
        sys.exit(1)
    return True

def init_git_repo():
    """Initialize a git repository in the current directory"""
    print_header("Initializing git repository")
    
    # Check if .git already exists
    if os.path.exists(".git"):
        print("Git repository already initialized")
        return True
    
    print("$ git init")
    output, success = run_command("git init")
    
    return success

def commit_changes():
    """Commit all changes to git"""
    print_header("Committing changes")
    
    print("$ git add .")
    output, success = run_command("git add .")
    
    print("$ git commit -m \"Prepare for Railway deployment\"")
    output, success = run_command("git commit -m \"Prepare for Railway deployment\"")
    
    if "nothing to commit" in output:
        print("No changes to commit")
        return True
    
    return success

def setup_webhook(app_url, bot_token):
    """Set up the webhook for the Telegram bot"""
    print_header("Setting up webhook")
    
    webhook_url = f"{app_url}/webhook"
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}"
    
    print(f"Setting webhook to: {webhook_url}")
    
    # Use Python's requests library
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            print("Webhook set successfully!")
            print(response.text)
            return True
        else:
            print(f"Failed to set webhook: {response.text}")
            return False
    except Exception as e:
        print(f"Error setting webhook: {str(e)}")
        return False

def create_env_file(bot_token):
    """Create a .env file with the bot token"""
    print_header("Creating .env file for Railway")
    
    with open(".env", "w") as f:
        f.write(f"BOT_TOKEN={bot_token}\n")
    
    print("Created .env file with BOT_TOKEN")
    return True

def create_procfile():
    """Create a Procfile for Railway if it doesn't exist"""
    if not os.path.exists("Procfile"):
        print_header("Creating Procfile for Railway")
        
        with open("Procfile", "w") as f:
            f.write("web: python app.py\n")
        
        print("Created Procfile")
    else:
        print("Procfile already exists")
    
    return True

def open_railway_website():
    """Open Railway website for deployment"""
    print_header("Opening Railway website")
    
    railway_url = "https://railway.app/"
    webbrowser.open(railway_url)
    
    return True

def main():
    """Main deployment function"""
    print("Screenshot Manager Bot Server - Railway Deployment Helper")
    print("------------------------------------------------------\n")
    
    # Check prerequisites
    check_git()
    
    # Get bot token
    print_header("Enter your Telegram Bot Token")
    bot_token = input("Bot Token: ").strip()
    
    # Prepare files for Railway
    create_env_file(bot_token)
    create_procfile()
    
    # Initialize Git if needed
    init_git_repo()
    commit_changes()
    
    # Guide user through Railway deployment
    print_header("Railway Deployment Instructions")
    print("1. Create a GitHub repository for this project (if you haven't already)")
    print("2. Push your code to GitHub")
    print("3. Sign up or log in to Railway (https://railway.app) using your GitHub account")
    print("4. Create a new project and select 'Deploy from GitHub repo'")
    print("5. Connect your GitHub account and select this repository")
    print("6. Railway will automatically deploy your application")
    
    proceed = input("\nWould you like to open the Railway website now? (y/n): ").strip().lower()
    if proceed == 'y':
        open_railway_website()
    
    print("\nAfter deployment on Railway, enter your app URL:")
    app_url = input("App URL (e.g., https://your-app-name.up.railway.app): ").strip()
    
    if app_url:
        setup_webhook(app_url, bot_token)
    
    print("\n------------------------------------------------------")
    print("Deployment preparation complete! Follow the steps above to complete your Railway deployment.")
    print("------------------------------------------------------")

if __name__ == "__main__":
    main() 