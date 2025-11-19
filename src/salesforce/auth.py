"""Salesforce authentication module"""
import logging
import webbrowser
import json
import os
import time
from urllib.parse import urlparse, parse_qs
from simple_salesforce import Salesforce
import requests
import http.server
import socketserver
import threading
import hashlib
import base64
import secrets


logger = logging.getLogger(__name__)

# OAuth configuration constants
OAUTH_PORT = 8080
OAUTH_REDIRECT_URI = f'http://localhost:{OAUTH_PORT}/oauth/callback'
OAUTH_TIMEOUT = 120  # 2 minutes
DEFAULT_API_VERSION = '65.0'

# HTML templates for OAuth callback responses
SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Authentication Successful</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px;
               background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .container { background: white; color: #333; padding: 40px; border-radius: 10px;
                     box-shadow: 0 10px 40px rgba(0,0,0,0.2); max-width: 500px; margin: 0 auto; }
        h1 { color: #28a745; margin-bottom: 20px; }
        p { font-size: 16px; line-height: 1.6; }
        .check { font-size: 60px; color: #28a745; }
    </style>
</head>
<body>
    <div class="container">
        <div class="check">✓</div>
        <h1>Authentication Successful!</h1>
        <p>You have successfully authenticated with Salesforce.</p>
        <p>You can now close this window and return to the application.</p>
    </div>
    <script>setTimeout(function() { window.close(); }, 3000);</script>
</body>
</html>"""

ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Authentication Failed</title>
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; }}
        .container {{ background: white; color: #333; padding: 40px; border-radius: 10px;
                      box-shadow: 0 10px 40px rgba(0,0,0,0.2); max-width: 500px; margin: 0 auto; }}
        h1 {{ color: #dc3545; margin-bottom: 20px; }}
        p {{ font-size: 16px; line-height: 1.6; }}
        .error {{ font-size: 60px; color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error">✗</div>
        <h1>Authentication Failed</h1>
        <p>{error_desc}</p>
        <p>You can close this window and try again.</p>
    </div>
</body>
</html>"""


class SalesforceAuth:
    """Handle Salesforce authentication"""
    
    def __init__(self, config: dict):
        """
        Initialize authentication handler
        
        Args:
            config: Salesforce configuration dictionary
        """
        self.config = config
        self.session = None
        self.config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
    
    def _get_auth_url(self) -> str:
        """Get base authentication URL based on domain configuration"""
        domain = self.config.get('domain', 'login')
        if domain in ['login', 'test']:
            return f"https://{domain}.salesforce.com"
        return f"https://{domain}.my.salesforce.com"
    
    def _save_oauth_tokens(self, access_token: str, instance_url: str, refresh_token: str | None = None):
        """Save OAuth tokens to config file without rewriting entire file"""
        # Update in-memory config
        if 'oauth' not in self.config:
            self.config['oauth'] = {}
        self.config['oauth']['access_token'] = access_token
        self.config['oauth']['instance_url'] = instance_url
        if refresh_token:
            self.config['oauth']['refresh_token'] = refresh_token
        
        # Update config file preserving structure
        with open(self.config_path, 'r') as f:
            file_config = json.load(f)
        
        if 'oauth' not in file_config:
            file_config['oauth'] = {}
        file_config['oauth']['access_token'] = access_token
        file_config['oauth']['instance_url'] = instance_url
        if refresh_token:
            file_config['oauth']['refresh_token'] = refresh_token
        
        with open(self.config_path, 'w') as f:
            json.dump(file_config, f, indent=2)
    
    def authenticate(self) -> Salesforce:
        """
        Authenticate with Salesforce using OAuth 2.0 with PKCE (for SSO)
        Opens browser for user authentication, automatically captures callback
        
        Returns:
            Salesforce session object
        """
        try:
            logger.info("Authenticating using OAuth 2.0 (SSO)...")
            oauth_config = self.config.get('oauth', {})
            
            # Try refresh token first (faster than access token validation)
            if oauth_config.get('refresh_token'):
                try:
                    logger.info("Attempting authentication with refresh token...")
                    return self._authenticate_refresh_token(oauth_config)
                except Exception as e:
                    logger.info(f"Refresh token authentication failed: {e}")
            
            # Try access token if refresh token failed or doesn't exist
            if oauth_config.get('access_token'):
                try:
                    logger.info("Attempting authentication with access token...")
                    return self._authenticate_with_access_token(oauth_config)
                except Exception as e:
                    logger.info(f"Access token authentication failed: {e}")
            
            # Start interactive OAuth flow with PKCE as last resort
            logger.info("Starting interactive OAuth flow...")
            return self._authenticate_oauth_interactive(oauth_config)
            
        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise
    
    def _authenticate_with_access_token(self, oauth_config: dict) -> Salesforce:
        """Authenticate using stored access token"""
        access_token = oauth_config.get('access_token')
        instance_url = oauth_config.get('instance_url')
        
        if not access_token or not instance_url:
            raise ValueError("Missing access_token or instance_url in config")
        
        self.session = Salesforce(
            instance_url=instance_url,
            session_id=access_token,
            version=self.config.get('api_version', DEFAULT_API_VERSION)
        )
        
        # Test if the access token is valid by making a simple query
        try:
            # Simple query to validate token
            self.session.query("SELECT Id FROM User LIMIT 1")
            logger.info(f"✓ Connected to: {instance_url}")
            return self.session
        except Exception as e:
            logger.info(f"Access token validation failed: {e}")
            raise ValueError(f"Access token is invalid or expired: {e}")
    
    def _authenticate_oauth_interactive(self, oauth_config: dict) -> Salesforce:
        """Interactive OAuth flow with browser and local callback server"""
        client_id = oauth_config.get('client_id')
        client_secret = oauth_config.get('client_secret')
        
        if not client_id:
            raise ValueError(
                "OAuth client_id not found in config.json.\n"
                "Add:\n"
                '"oauth": {\n'
                '  "client_id": "YOUR_CONNECTED_APP_CLIENT_ID",\n'
                '  "client_secret": "YOUR_CONSUMER_SECRET"\n'
                '}'
            )
        
        auth_url_base = self._get_auth_url()
        
        # Generate PKCE code verifier and challenge
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        # Build authorization URL with PKCE
        auth_url = (
            f"{auth_url_base}/services/oauth2/authorize?"
            f"response_type=code&"
            f"client_id={client_id}&"
            f"redirect_uri={OAUTH_REDIRECT_URI}&"
            f"code_challenge={code_challenge}&"
            f"code_challenge_method=S256"
        )
        
        logger.info(f"Starting local callback server on port {OAUTH_PORT}...")
        
        # Start local server to capture OAuth callback
        auth_result = {'code': None, 'error': None, 'received': False, 'code_verifier': code_verifier}
        server_thread = threading.Thread(
            target=self._start_oauth_server,
            args=(auth_result,),
            daemon=True
        )
        server_thread.start()
        
        time.sleep(0.5)  # Wait for server to start
        
        logger.info("Opening browser for SSO login...")
        logger.info("Please complete the login in your browser...")
        webbrowser.open(auth_url)
        
        # Wait for callback with timeout
        for i in range(OAUTH_TIMEOUT * 10):  # Check every 100ms
            if auth_result['received']:
                break
            time.sleep(0.1)
        
        if auth_result['error']:
            raise Exception(f"Authentication failed: {auth_result['error']}")
        if not auth_result['code']:
            raise Exception(f"Authentication timed out after {OAUTH_TIMEOUT // 60} minutes")
        
        logger.info("✓ Authorization code received")
        logger.info("Exchanging authorization code for access token...")
        
        token_data = {
            'grant_type': 'authorization_code',
            'code': auth_result['code'],
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': OAUTH_REDIRECT_URI,
            'code_verifier': auth_result['code_verifier']
        }
        
        response = requests.post(f"{auth_url_base}/services/oauth2/token", data=token_data)
        if response.status_code != 200:
            error_msg = response.json().get('error_description', 'Unknown error')
            raise Exception(f"Token exchange failed: {error_msg}")
        
        token_response = response.json()
        logger.info(f"✓ Authentication successful! Instance: {token_response['instance_url']}")
        
        self._save_oauth_tokens(
            token_response['access_token'],
            token_response['instance_url'],
            token_response.get('refresh_token')
        )
        logger.info("✓ Tokens saved to config.json")
        
        self.session = Salesforce(
            instance_url=token_response['instance_url'],
            session_id=token_response['access_token'],
            version=self.config.get('api_version', DEFAULT_API_VERSION)
        )
        
        return self.session
    
    def _start_oauth_server(self, auth_result):
        """Start a local HTTP server to capture OAuth callback"""
        
        class OAuthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler_self):
                """Handle GET request from OAuth callback"""
                try:
                    # Parse query parameters
                    parsed_path = urlparse(handler_self.path)
                    
                    if parsed_path.path == '/oauth/callback':
                        params = parse_qs(parsed_path.query)
                        
                        if 'code' in params:
                            auth_result['code'] = params['code'][0]
                            auth_result['received'] = True
                            handler_self.send_response(200)
                            handler_self.send_header('Content-type', 'text/html; charset=utf-8')
                            handler_self.end_headers()
                            handler_self.wfile.write(SUCCESS_HTML.encode('utf-8'))
                            
                        elif 'error' in params:
                            error_desc = params.get('error_description', [params['error'][0]])[0]
                            auth_result['error'] = error_desc
                            auth_result['received'] = True
                            handler_self.send_response(200)
                            handler_self.send_header('Content-type', 'text/html; charset=utf-8')
                            handler_self.end_headers()
                            handler_self.wfile.write(ERROR_HTML_TEMPLATE.format(error_desc=error_desc).encode('utf-8'))
                        
                        # Shutdown server after receiving callback
                        threading.Thread(target=handler_self.server.shutdown, daemon=True).start()
                    else:
                        # 404 for other paths
                        handler_self.send_response(404)
                        handler_self.end_headers()
                        
                except Exception as e:
                    auth_result['error'] = f"Server error: {str(e)}"
                    auth_result['received'] = True
            
            def log_message(handler_self, format, *args):
                """Suppress server log messages"""
                pass
        
        try:
            with socketserver.TCPServer(("", OAUTH_PORT), OAuthHandler) as httpd:
                httpd.serve_forever()
        except Exception as e:
            auth_result['error'] = f"Failed to start server on port {OAUTH_PORT}: {str(e)}"
            auth_result['received'] = True
    
    def _authenticate_refresh_token(self, oauth_config: dict) -> Salesforce:
        """Authenticate using stored refresh token"""
        data = {
            'grant_type': 'refresh_token',
            'client_id': oauth_config['client_id'],
            'client_secret': oauth_config['client_secret'],
            'refresh_token': oauth_config['refresh_token']
        }
        
        response = requests.post(f"{self._get_auth_url()}/services/oauth2/token", data=data)
        response.raise_for_status()
        
        token_data = response.json()
        self._save_oauth_tokens(token_data['access_token'], token_data['instance_url'])
        
        self.session = Salesforce(
            instance_url=token_data['instance_url'],
            session_id=token_data['access_token'],
            version=self.config.get('api_version', DEFAULT_API_VERSION)
        )
        
        logger.info(f"✓ Connected to: {token_data['instance_url']}")
        return self.session
    
    def get_instance_url(self) -> str | None:
        """Get Salesforce instance URL"""
        if self.session:
            return f"https://{self.session.sf_instance}"
        return None
    
    def get_session_id(self) -> str | None:
        """Get session ID"""
        if self.session:
            return self.session.session_id
        return None


def get_authenticated_client(config: dict):
    """
    Get an authenticated Salesforce REST client
    
    Args:
        config: Configuration dictionary containing Salesforce settings
        
    Returns:
        SalesforceRestClient: Authenticated REST client instance
    """
    from .rest_client import SalesforceRestClient
    
    auth = SalesforceAuth(config['salesforce'])
    auth.authenticate()
    
    return SalesforceRestClient(auth.session, config)
