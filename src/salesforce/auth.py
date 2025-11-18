"""Salesforce authentication module"""
import logging
import webbrowser
from urllib.parse import quote, urlparse, parse_qs
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
import requests
import http.server
import socketserver
import threading
import hashlib
import base64
import secrets


logger = logging.getLogger(__name__)

# Global authentication cache to avoid multiple authentications
_auth_cache = {}


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
    
    def authenticate(self) -> Salesforce:
        """
        Authenticate with Salesforce using configured method
        
        Returns:
            Salesforce session object
            
        Raises:
            SalesforceAuthenticationFailed: If authentication fails
        """
        auth_method = self.config.get('auth_method', 'oauth')
        
        if auth_method == 'oauth':
            return self._authenticate_oauth()
        else:
            return self._authenticate_password()
    
    def _authenticate_password(self) -> Salesforce:
        """
        Authenticate with Salesforce using username/password/token
        
        Returns:
            Salesforce session object
        """
        try:
            logger.debug(f"Authenticating as {self.config['username']} using password")
            
            self.session = Salesforce(
                username=self.config['username'],
                password=self.config['password'],
                security_token=self.config['security_token'],
                domain=self.config['domain'],
                version=self.config['api_version']
            )
            
            logger.debug(f"Connected to: {self.session.sf_instance}")
            logger.debug(f"Session ID: {self.session.session_id[:20]}...")
            
            return self.session
            
        except SalesforceAuthenticationFailed as e:
            logger.error(f"Authentication failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            raise
    

    
    def _authenticate_oauth(self) -> Salesforce:
        """
        Authenticate with Salesforce using OAuth 2.0 with PKCE (for SSO)
        Opens browser for user authentication, automatically captures callback
        
        Returns:
            Salesforce session object
        """
        try:
            logger.info("Authenticating using OAuth 2.0 (SSO)...")
            
            # Try refresh token first (faster than access token validation)
            if self.config.get('oauth', {}).get('refresh_token'):
                try:
                    logger.info("Attempting authentication with refresh token...")
                    return self._authenticate_refresh_token()
                except Exception as e:
                    logger.info(f"Refresh token authentication failed: {e}")
            
            # Try access token if refresh token failed or doesn't exist
            if self.config.get('oauth', {}).get('access_token'):
                try:
                    logger.info("Attempting authentication with access token...")
                    return self._authenticate_with_access_token()
                except Exception as e:
                    logger.info(f"Access token authentication failed: {e}")
            
            # Start interactive OAuth flow with PKCE as last resort
            logger.info("Starting interactive OAuth flow...")
            return self._authenticate_oauth_interactive()
            
        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise
    
    def _authenticate_with_access_token(self) -> Salesforce:
        """Authenticate using stored access token"""
        logger.info("Authenticating with stored access token...")
        
        oauth_config = self.config.get('oauth', {})
        access_token = oauth_config.get('access_token')
        instance_url = oauth_config.get('instance_url')
        
        if not access_token or not instance_url:
            raise ValueError("Missing access_token or instance_url in config")
        
        self.session = Salesforce(
            instance_url=instance_url,
            session_id=access_token,
            version=self.config.get('api_version', '65.0')
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
    
    def _authenticate_oauth_interactive(self) -> Salesforce:
        """Interactive OAuth flow with browser and local callback server"""
        logger.info("Starting interactive OAuth flow...")
        
        # Get OAuth config
        oauth_config = self.config.get('oauth', {})
        client_id = oauth_config.get('client_id')
        client_secret = oauth_config.get('client_secret')
        redirect_uri = 'http://localhost:8080/oauth/callback'
        
        if not client_id:
            raise ValueError(
                "OAuth client_id not found in config.json.\n"
                "Add:\n"
                '"oauth": {\n'
                '  "client_id": "YOUR_CONNECTED_APP_CLIENT_ID",\n'
                '  "client_secret": "YOUR_CONSUMER_SECRET"\n'
                '}'
            )
        
        # Determine Salesforce domain
        domain = self.config.get('domain', 'login')
        if domain not in ['login', 'test']:
            auth_url_base = f"https://{domain}.my.salesforce.com"
        else:
            auth_url_base = f"https://{domain}.salesforce.com"
        
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
            f"redirect_uri={redirect_uri}&"
            f"code_challenge={code_challenge}&"
            f"code_challenge_method=S256"
        )
        
        logger.info("Starting local callback server on port 8080...")
        
        # Start local server to capture OAuth callback
        auth_result = {'code': None, 'error': None, 'received': False, 'code_verifier': code_verifier}
        server_thread = threading.Thread(
            target=self._start_oauth_server,
            args=(auth_result,),
            daemon=True
        )
        server_thread.start()
        
        # Wait a moment for server to start
        import time
        time.sleep(0.5)
        
        logger.info("Opening browser for SSO login...")
        logger.info("Please complete the login in your browser...")
        
        # Open browser
        webbrowser.open(auth_url)
        
        # Wait for callback (with timeout)
        timeout = 120  # 2 minutes
        for i in range(timeout * 10):  # Check every 100ms
            if auth_result['received']:
                break
            time.sleep(0.1)
        
        if auth_result['error']:
            raise Exception(f"Authentication failed: {auth_result['error']}")
        
        if not auth_result['code']:
            raise Exception("Authentication timed out after 2 minutes")
        
        auth_code = auth_result['code']
        code_verifier = auth_result['code_verifier']
        logger.info("✓ Authorization code received")
        
        # Exchange authorization code for access token with PKCE
        logger.info("Exchanging authorization code for access token...")
        token_url = f"{auth_url_base}/services/oauth2/token"
        token_data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'code_verifier': code_verifier
        }
        
        response = requests.post(token_url, data=token_data)
        if response.status_code != 200:
            error_msg = response.json().get('error_description', 'Unknown error')
            raise Exception(f"Token exchange failed: {error_msg}")
        
        token_response = response.json()
        access_token = token_response['access_token']
        instance_url = token_response['instance_url']
        refresh_token = token_response.get('refresh_token', '')
        
        logger.info("✓ Authentication successful!")
        logger.info(f"Instance URL: {instance_url}")
        
        # Update config with new tokens
        if 'oauth' not in self.config:
            self.config['oauth'] = {}
        
        self.config['oauth']['access_token'] = access_token
        self.config['oauth']['instance_url'] = instance_url
        if refresh_token:
            self.config['oauth']['refresh_token'] = refresh_token
        
        # Save config to file
        import os
        import json
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        
        logger.info("✓ Tokens saved to config.json")
        
        # Create Salesforce session
        self.session = Salesforce(
            instance_url=instance_url,
            session_id=access_token,
            version=self.config.get('api_version', '65.0')
        )
        
        return self.session
    
    def _start_oauth_server(self, auth_result):
        """Start a local HTTP server to capture OAuth callback"""
        port = 8080
        
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
                            
                            # Send success response
                            handler_self.send_response(200)
                            handler_self.send_header('Content-type', 'text/html; charset=utf-8')
                            handler_self.end_headers()
                            handler_self.wfile.write("""
                                <!DOCTYPE html>
                                <html>
                                <head>
                                    <title>Authentication Successful</title>
                                    <style>
                                        body { 
                                            font-family: Arial, sans-serif; 
                                            text-align: center; 
                                            padding: 50px;
                                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                            color: white;
                                        }
                                        .container {
                                            background: white;
                                            color: #333;
                                            padding: 40px;
                                            border-radius: 10px;
                                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                                            max-width: 500px;
                                            margin: 0 auto;
                                        }
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
                                    <script>
                                        // Auto-close after 3 seconds
                                        setTimeout(function() { window.close(); }, 3000);
                                    </script>
                                </body>
                                </html>
                            """.encode('utf-8'))
                            
                        elif 'error' in params:
                            error_desc = params.get('error_description', [params['error'][0]])[0]
                            auth_result['error'] = error_desc
                            auth_result['received'] = True
                            
                            # Send error response
                            handler_self.send_response(200)
                            handler_self.send_header('Content-type', 'text/html; charset=utf-8')
                            handler_self.end_headers()
                            handler_self.wfile.write(f"""
                                <!DOCTYPE html>
                                <html>
                                <head>
                                    <title>Authentication Failed</title>
                                    <style>
                                        body {{ 
                                            font-family: Arial, sans-serif; 
                                            text-align: center; 
                                            padding: 50px;
                                            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                                            color: white;
                                        }}
                                        .container {{
                                            background: white;
                                            color: #333;
                                            padding: 40px;
                                            border-radius: 10px;
                                            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                                            max-width: 500px;
                                            margin: 0 auto;
                                        }}
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
                                </html>
                            """.encode('utf-8'))
                        
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
            with socketserver.TCPServer(("", port), OAuthHandler) as httpd:
                httpd.serve_forever()
        except Exception as e:
            auth_result['error'] = f"Failed to start server on port {port}: {str(e)}"
            auth_result['received'] = True
    
    def _authenticate_refresh_token(self) -> Salesforce:
        """Authenticate using stored refresh token"""
        logger.info("Authenticating with refresh token...")
        
        oauth_config = self.config.get('oauth', {})
        refresh_token = oauth_config.get('refresh_token')
        client_id = oauth_config.get('client_id')
        client_secret = oauth_config.get('client_secret')
        
        domain = self.config.get('domain', 'login')
        
        # Determine the instance URL based on domain
        if domain in ['login', 'test']:
            instance_url = f"https://{domain}.salesforce.com"
        else:
            # My Domain or custom domain
            instance_url = f"https://{domain}.my.salesforce.com"
        
        # Get new access token using refresh token
        token_url = f"{instance_url}/services/oauth2/token"
        
        data = {
            'grant_type': 'refresh_token',
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        
        # Update stored access token
        self.config['oauth']['access_token'] = token_data['access_token']
        self.config['oauth']['instance_url'] = token_data['instance_url']
        
        # Save to config
        import os
        import json
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        
        self.session = Salesforce(
            instance_url=token_data['instance_url'],
            session_id=token_data['access_token'],
            version=self.config.get('api_version', '65.0')
        )
        
        logger.info(f"✓ Connected to: {token_data['instance_url']}")
        return self.session
    
    def _authenticate_web_server_flow(self) -> Salesforce:
        """Authenticate using OAuth web server flow (opens browser)"""
        logger.info("Starting OAuth web server flow...")
        logger.info("A browser window will open for you to login...")
        
        domain = self.config.get('domain', 'login')
        if domain not in ['login', 'test']:
            auth_url_base = f"https://{domain}.my.salesforce.com"
        else:
            auth_url_base = f"https://{domain}.salesforce.com"
        
        # Build authorization URL
        redirect_uri = self.config.get('redirect_uri', 'http://localhost:8080/callback')
        
        auth_url = (
            f"{auth_url_base}/services/oauth2/authorize"
            f"?response_type=code"
            f"&client_id={self.config['client_id']}"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&scope=api%20refresh_token%20offline_access"
        )
        
        logger.info(f"Opening browser to: {auth_url}")
        logger.info(f"Using redirect URI: {redirect_uri}")
        webbrowser.open(auth_url)
        
        logger.info("\n" + "="*80)
        logger.info("AUTHORIZATION INSTRUCTIONS:")
        logger.info("="*80)
        logger.info("1. A browser window should open for Salesforce login")
        logger.info("2. Log in using your SSO credentials")
        logger.info("3. Click 'Allow' to authorize the app")
        logger.info("4. After authorization, you'll be redirected")
        logger.info("5. Copy the FULL URL from your browser's address bar")
        logger.info("6. Paste it below")
        logger.info("="*80)
        logger.info("\nThe URL will look like:")
        logger.info(f"  {redirect_uri}?code=aPrx...")
        logger.info("="*80 + "\n")
        
        callback_url = input("Paste the full callback URL here: ").strip()
        
        # Extract authorization code
        if 'code=' not in callback_url:
            raise ValueError("Invalid callback URL - no authorization code found")
        
        code = callback_url.split('code=')[1].split('&')[0]
        logger.info(f"Authorization code received: {code[:20]}...")
        
        # Exchange code for tokens
        token_url = f"{auth_url_base}/services/oauth2/token"
        
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'redirect_uri': redirect_uri,
            'code': code
        }
        
        logger.info(f"Exchanging authorization code for access token...")
        response = requests.post(token_url, data=data)
        
        if not response.ok:
            logger.error(f"Token exchange failed: {response.text}")
            response.raise_for_status()
        
        token_data = response.json()
        
        logger.info(f"\n{'='*80}")
        logger.info("✓ Successfully authenticated!")
        logger.info(f"{'='*80}")
        logger.info(f"Instance: {token_data['instance_url']}")
        logger.info(f"\nIMPORTANT: Save this refresh token to your config.json")
        logger.info(f"Add this line to the 'salesforce' section:")
        logger.info(f"  \"refresh_token\": \"{token_data['refresh_token']}\"")
        logger.info(f"{'='*80}\n")
        
        self.session = Salesforce(
            instance_url=token_data['instance_url'],
            session_id=token_data['access_token'],
            version=self.config['api_version']
        )
        
        return self.session
    
    def get_instance_url(self) -> str:
        """Get Salesforce instance URL"""
        if self.session:
            return f"https://{self.session.sf_instance}"
        return None
    
    def get_session_id(self) -> str:
        """Get session ID"""
        if self.session:
            return self.session.session_id
        return None


def get_authenticated_client(config: dict, force_new=False):
    """
    Helper function to get an authenticated Salesforce REST client
    Uses cached authentication to avoid multiple auth calls
    
    Args:
        config: Configuration dictionary containing Salesforce settings
        force_new: Force new authentication even if cached session exists
        
    Returns:
        SalesforceRestClient: Authenticated REST client instance
    """
    from .rest_client import SalesforceRestClient
    
    # Create cache key from config
    cache_key = (
        config['salesforce'].get('username', ''),
        config['salesforce'].get('instance_url', ''),
        config['salesforce'].get('domain', '')
    )
    
    # Check if we have a cached auth instance
    if not force_new and cache_key in _auth_cache:
        auth = _auth_cache[cache_key]
        logger.debug("Using cached authentication session")
    else:
        auth = SalesforceAuth(config['salesforce'])
        sf_session = auth.authenticate()
        _auth_cache[cache_key] = auth
        logger.debug("Created new authentication session")
    
    return SalesforceRestClient(auth.session, config)
