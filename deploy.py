#!/usr/bin/env python
"""
Deployment script for the Screenshot Manager Bot server
"""
import os
import subprocess
import sys
import re
import time
import webbrowser

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

def check_heroku_cli():
    """Check if Heroku CLI is installed"""
    print_header("Checking if Heroku CLI is installed")
    print("$ heroku --version")
    output, success = run_command("heroku --version")
    
    if not success or "heroku" not in output.lower():
        print("Heroku CLI not found! Please install it from: https://devcenter.heroku.com/articles/heroku-cli")
        sys.exit(1)
    return True

def check_heroku_login():
    """Check if user is logged in to Heroku"""
    print_header("Checking if user is logged in to Heroku")
    print("$ heroku auth:whoami")
    output, success = run_command("heroku auth:whoami")
    
    if not success or "Error" in output:
        print("You're not logged in to Heroku. Please run 'heroku login' first.")
        run_command("heroku login")
        # Check again after login attempt
        output, success = run_command("heroku auth:whoami", silent=True)
        if not success:
            print("Failed to log in to Heroku. Please try manually with 'heroku login'")
            sys.exit(1)
    return True

def create_heroku_app(app_name):
    """Create a Heroku app with the given name"""
    print_header(f"Creating Heroku app: {app_name}")
    print(f"$ heroku apps:info --app {app_name} || heroku create {app_name}")
    
    # First check if the app already exists
    output, success = run_command(f"heroku apps:info --app {app_name}", silent=True)
    
    if success:
        print(f"App '{app_name}' already exists.")
        return True
    
    # App doesn't exist, try to create it
    output, success = run_command(f"heroku create {app_name}")
    
    if "verification_required" in output:
        print("\nHeroku requires account verification with payment information!")
        print("Please verify your account at: https://heroku.com/verify")
        webbrowser.open("https://heroku.com/verify")
        
        input("\nPress Enter after verifying your account to continue...")
        
        # Try again after verification
        output, success = run_command(f"heroku create {app_name}")
        if not success:
            print(f"Failed to create app '{app_name}'. Please try a different name or verify your account.")
            return False
    
    return success

def set_config_vars(app_name, bot_token):
    """Set environment variables for the Heroku app"""
    print_header("Setting environment variables")
    print(f"$ heroku config:set BOT_TOKEN={bot_token[:5]}... --app {app_name}")
    
    output, success = run_command(f"heroku config:set BOT_TOKEN={bot_token} --app {app_name}")
    
    return success

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

def setup_git_remote(app_name):
    """Set up the Heroku remote for git"""
    print_header("Adding Heroku remote")
    
    # Check if remote already exists
    output, success = run_command("git remote -v")
    if "heroku" in output:
        print("Heroku remote already configured")
        return True
    
    print(f"$ heroku git:remote --app {app_name}")
    output, success = run_command(f"heroku git:remote --app {app_name}")
    
    return success

def commit_changes():
    """Commit all changes to git"""
    print_header("Committing changes")
    
    print("$ git add .")
    output, success = run_command("git add .")
    
    print("$ git commit -m \"Deploy to Heroku\"")
    output, success = run_command("git commit -m \"Deploy to Heroku\"")
    
    if "nothing to commit" in output:
        print("No changes to commit")
        return True
    
    return success

def find_current_branch():
    """Find the current git branch"""
    output, success = run_command("git branch --show-current")
    if success and output.strip():
        return output.strip()
    
    # Fallback method for older git versions
    output, success = run_command("git branch")
    if success:
        for line in output.split('\n'):
            if line.startswith('*'):
                return line.replace('*', '').strip()
    
    return "master"  # Default fallback

def deploy_to_heroku():
    """Deploy the app to Heroku"""
    print_header("Deploying to Heroku")
    
    # Find current branch
    branch = find_current_branch()
    print(f"Current branch: {branch}")
    
    print(f"$ git push heroku {branch}:main -f")
    output, success = run_command(f"git push heroku {branch}:main -f")
    
    if not success:
        print("Failed to push to Heroku. Trying alternative approach...")
        print("$ git push heroku HEAD:main -f")
        output, success = run_command("git push heroku HEAD:main -f")
    
    return success

def setup_webhook(app_name, bot_token):
    """Set up the webhook for the Telegram bot"""
    print_header("Setting up webhook")
    
    webhook_url = f"https://{app_name}.herokuapp.com/webhook"
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}"
    
    print(f"Setting webhook to: {webhook_url}")
    
    # Use Python's requests if available, otherwise use curl
    try:
        import requests
        response = requests.get(api_url)
        success = response.status_code == 200
        print(response.text)
    except ImportError:
        command = f'curl "{api_url}"'
        output, success = run_command(command)
    
    return success

def main():
    """Main deployment function"""
    print("Screenshot Manager Bot Server - Heroku Deployment Helper")
    print("------------------------------------------------------\n")
    
    # Check prerequisites
    check_heroku_cli()
    check_heroku_login()
    
    # Get app info
    print_header("Enter your Heroku app name (e.g., screenshot-manager-bot)")
    app_name = input("App name: ").strip()
    
    print_header("Enter your Telegram Bot Token")
    bot_token = input("Bot Token: ").strip()
    
    # Deploy the app
    if not create_heroku_app(app_name):
        print("Failed to create Heroku app. Exiting.")
        sys.exit(1)
    
    if not set_config_vars(app_name, bot_token):
        print("Failed to set environment variables. Exiting.")
        sys.exit(1)
    
    if not init_git_repo():
        print("Failed to initialize git repository. Exiting.")
        sys.exit(1)
    
    if not setup_git_remote(app_name):
        print("Failed to set up Heroku remote. Exiting.")
        sys.exit(1)
    
    if not commit_changes():
        print("Warning: Failed to commit changes. This might be okay if you already committed.")
    
    if not deploy_to_heroku():
        print("Failed to deploy to Heroku. Please check the error messages.")
        sys.exit(1)
    
    if not setup_webhook(app_name, bot_token):
        print("Failed to set up webhook. Please set it up manually.")
        manual_webhook_url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url=https://{app_name}.herokuapp.com/webhook"
        print(f"Manual webhook URL: {manual_webhook_url}")
        sys.exit(1)
    
    print("\n------------------------------------------------------")
    print(f"Deployment successful! Your bot is now running at:")
    print(f"https://{app_name}.herokuapp.com/")
    print("------------------------------------------------------")

if __name__ == "__main__":
    main() 