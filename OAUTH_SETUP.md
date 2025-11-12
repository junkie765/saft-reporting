# OAuth SSO Setup Guide for Salesforce

This guide will help you set up OAuth authentication for SSO-enabled Salesforce orgs.

## Step 1: Create a Connected App in Salesforce

1. **Log in to Salesforce** (using your SSO)

2. **Navigate to Setup**
   - Click the gear icon → Setup

3. **Create Connected App**
   - In Quick Find, search for "App Manager"
   - Click "New Connected App"

4. **Fill in Basic Information**
   - **Connected App Name**: `SAF-T Export Tool`
   - **API Name**: `SAFT_Export_Tool` (auto-filled)
   - **Contact Email**: Your email

5. **Enable OAuth Settings**
   - Check "Enable OAuth Settings"
   - **Callback URL**: `http://localhost:8080/callback`
   - **Selected OAuth Scopes**: Add these scopes:
     - `Access and manage your data (api)`
     - `Perform requests on your behalf at any time (refresh_token, offline_access)`
   
6. **Save** the Connected App

7. **Get Consumer Key and Secret**
   - After saving, click "Manage Consumer Details"
   - You'll see:
     - **Consumer Key** (Client ID)
     - **Consumer Secret** (Client Secret)
   - Copy both values

## Step 2: Configure the Application

Edit `config.json`:

```json
{
  "salesforce": {
    "auth_method": "oauth",
    "domain": "login",
    "api_version": "59.0",
    "client_id": "YOUR_CONSUMER_KEY_HERE",
    "client_secret": "YOUR_CONSUMER_SECRET_HERE",
    "redirect_uri": "http://localhost:8080/callback",
    "refresh_token": ""
  }
}
```

**Domain Settings:**
- Use `"login"` for production orgs
- Use `"test"` for sandbox
- Use your My Domain name if applicable (e.g., `"yourcompany"`)

## Step 3: First-Time Authentication

Run the script:

```bash
python main.py --start-date 2024-01-01 --end-date 2024-12-31
```

**What happens:**
1. A browser window will open
2. Log in using your SSO (SAML, Microsoft, Google, etc.)
3. Authorize the app
4. You'll be redirected to a URL like: `http://localhost:8080/callback?code=...`
5. Copy the ENTIRE URL from your browser
6. Paste it into the terminal when prompted

**The script will:**
- Extract the authorization code
- Exchange it for an access token and refresh token
- Display the refresh token to save

## Step 4: Save the Refresh Token

After successful login, the script will display:

```
✓ Successfully authenticated!
Save this refresh token to your config.json for future use:
"refresh_token": "5Aep861..."
```

**Update your config.json:**

```json
{
  "salesforce": {
    "auth_method": "oauth",
    "domain": "login",
    "api_version": "59.0",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uri": "http://localhost:8080/callback",
    "refresh_token": "5Aep861rHorPRfeDtR3jUfBbZ4uGG7FGKBrPl..."
  }
}
```

## Step 5: Future Usage

Once you have the refresh token, the script will:
- Automatically refresh the access token
- No browser login required
- Works in headless environments

## Troubleshooting

### Error: "redirect_uri_mismatch"
- Ensure the redirect URI in config.json matches EXACTLY what's in the Connected App
- Default: `http://localhost:8080/callback`

### Error: "invalid_client_id"
- Verify the Consumer Key is correct in config.json
- Check that the Connected App is approved

### Error: "user hasn't approved this consumer"
- Go through the OAuth flow at least once
- Approve the app when prompted

### Connected App Not Working
- Wait 2-10 minutes after creating the Connected App
- Check that "API (Enable OAuth Settings)" is enabled
- Verify OAuth scopes include `api` and `refresh_token`

### IP Restrictions
If your org has IP restrictions:
1. In the Connected App settings
2. Go to "Manage" → "Edit Policies"
3. Set "IP Relaxation" to "Relax IP restrictions"

## Alternative: Using JWT Bearer Flow (Advanced)

For fully automated/headless authentication, you can use JWT Bearer flow with a certificate. This requires:
1. Uploading a certificate to the Connected App
2. Using the certificate to sign JWT tokens
3. More complex setup but no browser interaction

Let me know if you need help setting up JWT flow!

## Security Notes

- **Never commit** `config.json` with real credentials to version control
- Store refresh tokens securely
- Rotate Connected App secrets periodically
- Use restricted OAuth scopes when possible
- Consider using JWT Bearer flow for production automation
