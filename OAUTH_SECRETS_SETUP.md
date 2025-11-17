# OAuth Setup Guide

## Overview
The application supports OAuth SSO authentication with Salesforce. OAuth authentication happens **automatically** when you set `auth_method` to `"oauth"` in config.json - no button click required!

## Setup Instructions

### 1. Create Connected App in Salesforce

1. Log in to Salesforce as an administrator
2. Go to **Setup** → **Apps** → **App Manager**
3. Click **New Connected App**
4. Fill in the basic information:
   - **Connected App Name**: SAFT Reporting Tool
   - **API Name**: SAFT_Reporting_Tool
   - **Contact Email**: your-email@company.com

5. Enable OAuth Settings:
   - Check **Enable OAuth Settings**
   - **Callback URL**: `http://localhost:8080/oauth/callback`
   - **Selected OAuth Scopes**:
     - Full access (full)
     - Perform requests at any time (refresh_token, offline_access)
   - Check **Require Proof Key for Code Exchange (PKCE) Extension for Supported Authorization Flows** (optional, for extra security)

6. Click **Save**
7. Click **Continue**
8. Copy the **Consumer Key** (this is your `client_id`)
9. Click **Click to reveal** next to Consumer Secret and copy it (this is your `client_secret`)

### 2. Configure OAuth in config.json

Add OAuth credentials to your `config.json`:

```json
{
  "salesforce": {
    "auth_method": "oauth",
    "domain": "scalefocus",
    "api_version": "65.0",
    "oauth": {
      "client_id": "YOUR_CONSUMER_KEY_FROM_SALESFORCE",
      "client_secret": "YOUR_CONSUMER_SECRET_FROM_SALESFORCE"
    }
  }
}
```

### 3. Secure Your Secrets

**IMPORTANT**: Make sure `config.json` is in `.gitignore` to prevent committing secrets to version control:

```
*.pyc
__pycache__/
.venv/
*.log
output/
certs/*.p12
config.json
```

## How OAuth Authentication Works

Authentication happens **automatically** when you run the application with `auth_method: "oauth"`:

1. The application checks if you have a valid access token
2. If not, it checks for a refresh token and tries to get a new access token
3. If neither works, it automatically starts the interactive OAuth flow:
   - A local server starts on port 8080 to receive the OAuth callback
   - Your web browser automatically opens with Salesforce login page
   - Log in using your SSO credentials
   - After successful login, you'll be automatically redirected back
   - The browser shows a success page (you can close it)
   - The application automatically:
     - Captures the authorization code
     - Exchanges it for an access token (using PKCE for security)
     - Saves the tokens to `config.json`
     - Continues with loading companies and report generation

**No button clicks or manual code entry required!** The whole process is automatic.

## Token Storage

After successful authentication, tokens are stored in `config.json` inside the salesforce section:

```json
{
  "salesforce": {
    "auth_method": "oauth",
    "domain": "scalefocus",
    "api_version": "65.0",
    "oauth": {
      "client_id": "3MVG9...",
      "client_secret": "ABC123...",
      "access_token": "00D...!AR...",
      "instance_url": "https://scalefocus.my.salesforce.com",
      "refresh_token": "5Aep..."
    }
  }
}
```

## Token Expiration

- **Access Token**: Expires after a few hours. Use the **Authenticate** button to get a new one.
- **Refresh Token**: Lasts much longer (until revoked). Can be used to get new access tokens programmatically (future enhancement).

## Security Best Practices

1. ✅ **Store OAuth credentials in `config.json`** under the `oauth` section
2. ✅ **Add `config.json` to `.gitignore`** to prevent committing secrets
3. ✅ **Never commit secrets to version control**
4. ✅ **Rotate secrets periodically** (update Connected App in Salesforce)
5. ✅ **Limit OAuth scopes** to only what's needed
6. ✅ **Refresh tokens are automatically used** - no frequent re-authentication needed!

## Troubleshooting

### "OAuth client_id not found" Error
- Make sure `config.json` contains the `oauth` section
- Check that the section has valid `client_id` and `client_secret`

### "Token exchange failed" Error
- Make sure the redirect URI in Connected App matches: `http://localhost:8080/oauth/callback`
- Check that the Connected App is approved for use
- Verify PKCE is enabled or allowed in your Connected App settings

### "Authentication Failed" in Browser
- Ensure you have the correct permissions in Salesforce
- Verify the Connected App is not restricted by IP ranges or profiles
- Check with your Salesforce administrator if SSO policies are blocking access

## Current Features

- ✅ Automatic refresh token usage (no manual re-authentication needed)
- ✅ Token expiration detection and auto-refresh
- ✅ PKCE (Proof Key for Code Exchange) for enhanced security
- ✅ Automatic browser-based authentication flow

## Future Enhancements

- Multiple user profile support
- Encrypted credential storage
