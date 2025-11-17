"""Salesforce authentication module"""
import logging
import webbrowser
from urllib.parse import quote
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
import requests


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
        auth_method = self.config.get('auth_method', 'password')
        
        if auth_method == 'oauth':
            return self._authenticate_oauth()
        elif auth_method == 'session_id':
            return self._authenticate_session_id()
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
    
    def _authenticate_session_id(self) -> Salesforce:
        """
        Authenticate using a Session ID from browser (EASIEST for SSO!)
        
        Returns:
            Salesforce session object
        """
        try:
            logger.info("Authenticating using Session ID...")
            
            session_id = self.config.get('session_id')
            instance_url = self.config.get('instance_url')
            
            if not session_id:
                logger.error("\n" + "="*80)
                logger.error("ERROR: No session_id found in config.json")
                logger.error("="*80)
                logger.info("\nTo get your Session ID (takes 30 seconds):")
                logger.info("")
                logger.info("1. Open Salesforce in your browser (log in with SSO)")
                logger.info("2. Press F12 to open Developer Tools")
                logger.info("3. Click the 'Console' tab")
                logger.info("4. Type this command and press Enter:")
                logger.info("")
                logger.info("   console.log($Api.getSessionId())")
                logger.info("")
                logger.info("5. Copy the Session ID (long string starting with '00D')")
                logger.info("6. Add to config.json:")
                logger.info("")
                logger.info('   "session_id": "YOUR_SESSION_ID_HERE"')
                logger.info("")
                logger.info("="*80 + "\n")
                raise ValueError("session_id is required for this auth method")
            
            if not instance_url:
                domain = self.config.get('domain', 'scalefocus')
                if domain in ['login', 'test']:
                    instance_url = f"https://{domain}.salesforce.com"
                else:
                    instance_url = f"https://{domain}.my.salesforce.com"
            
            logger.info(f"Connecting to: {instance_url}")
            
            self.session = Salesforce(
                instance_url=instance_url,
                session_id=session_id,
                version=self.config['api_version']
            )
            
            logger.info("✓ Session ID authentication successful")
            return self.session
            
        except Exception as e:
            logger.error(f"Session ID authentication failed: {e}")
            raise
    
    def _authenticate_oauth(self) -> Salesforce:
        """
        Authenticate with Salesforce using OAuth 2.0 (for SSO)
        
        Returns:
            Salesforce session object
        """
        try:
            logger.info("Authenticating using OAuth 2.0 (SSO)...")
            
            # Check if we have a refresh token
            if self.config.get('refresh_token'):
                return self._authenticate_refresh_token()
            
            # Try to use client credentials flow (no user interaction)
            logger.warning("No refresh_token found. OAuth requires manual authorization.")
            logger.warning("Please add a refresh_token to your config.json to use OAuth authentication.")
            logger.warning("Alternatively, change auth_method to 'password' if you have username/password.")
            raise ValueError("OAuth authentication requires a refresh_token in config.json")
            
        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise
    
    def _authenticate_refresh_token(self) -> Salesforce:
        """Authenticate using stored refresh token"""
        logger.info("Authenticating with refresh token...")
        
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
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'refresh_token': self.config['refresh_token']
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        
        self.session = Salesforce(
            instance_url=token_data['instance_url'],
            session_id=token_data['access_token'],
            version=self.config['api_version']
        )
        
        logger.info(f"Connected to: {token_data['instance_url']}")
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
