# Setup Guide - SAF-T Bulgaria Export

## Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Configure Salesforce Credentials

### 2.1 Create Configuration File

```bash
# Copy the example configuration
cp config.example.json config.json
```

### 2.2 Get Salesforce Security Token

1. Log in to Salesforce
2. Click on your profile picture → Settings
3. In Quick Find, search for "Reset My Security Token"
4. Click "Reset Security Token"
5. Check your email for the new security token

### 2.3 Update config.json

Edit `config.json` with your credentials:

```json
{
  "salesforce": {
    "username": "your.email@company.com",
    "password": "YourPassword123",
    "security_token": "AbCdEfGhIjKlMnOpQrStU",
    "domain": "login",
    "api_version": "59.0"
  }
}
```

**Domain Settings:**
- **Production Org**: `"login"`
- **Sandbox**: `"test"` 
- **My Domain**: `"yourcompany"` (just the domain name, not full URL)

## Step 3: Verify Salesforce Permissions

Ensure your Salesforce user has:

1. **API Enabled** - Required for API access
2. **View All Data** or read permission on:
   - Accounts
   - Certinia General Ledger Accounts (`c2g__codaGeneralLedgerAccount__c`)
   - Certinia Journal Entries (`c2g__codaJournal__c`)
   - Certinia Journal Line Items (`c2g__codaJournalLineItem__c`)
   - Certinia Transactions (`c2g__codaTransaction__c`)
   - Certinia Company (`c2g__codaCompany__c`)

## Step 4: Update Company Information

Edit the `saft` section in `config.json`:

```json
{
  "saft": {
    "company_name": "Your Company Name Ltd",
    "tax_registration_number": "BG123456789",
    "company_id": "123456789",
    "fiscal_year": 2024,
    "selection_start_date": "2024-01-01",
    "selection_end_date": "2024-12-31"
  }
}
```

## Step 5: Test the Connection

Run a test export for a small date range:

```bash
python main.py --start-date 2024-01-01 --end-date 2024-01-31
```

## Step 6: Run Full Export

For a full year:

```bash
python main.py --start-date 2024-01-01 --end-date 2024-12-31
```

The SAF-T XML file will be created in the `output/` directory.

## Common Issues

### Issue: "Invalid username, password, security token"

**Solutions:**
1. Verify credentials are correct in config.json
2. Reset security token and update config.json
3. Check if account is locked
4. Verify API Enabled permission

### Issue: "Object does not exist"

**Solutions:**
1. Ensure Certinia Finance Cloud is installed
2. Check object API names in the `certinia.objects` section
3. Verify you have read permissions on these objects

### Issue: "Timeout errors"

**Solutions:**
1. Increase `timeout` value in `bulk_api` section (default 3600 seconds)
2. Reduce date range
3. Check Salesforce org limits

## Support

For issues:
1. Check the `TROUBLESHOOTING.md` file
2. Review Salesforce debug logs
3. Check Bulk Data Load Jobs in Salesforce Setup
