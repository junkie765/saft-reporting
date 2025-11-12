# SAF-T Reporting for Bulgaria - Certinia Finance Cloud

This project extracts financial data from Salesforce (Certinia Finance Cloud) using Bulk API 2.0 and transforms it into SAF-T (Standard Audit File for Tax) XML format compliant with Bulgarian requirements.

## Features

- Connects to Salesforce using OAuth 2.0 or Session ID authentication
- Extracts large datasets using Salesforce Bulk API 2.0
- Transforms Certinia Finance Cloud data into SAF-T XML format
- Supports Bulgarian SAF-T schema requirements (V 1.0.1)
- Automatically extracts company data from Salesforce (no config file needed)
- Handles Cyrillic characters correctly (UTF-8 encoding)
- Company filtering by name
- Handles data pagination and large file processing

## Prerequisites

- Python 3.8 or higher
- Salesforce Connected App credentials
- Access to Certinia Finance Cloud objects

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

1. Copy `config.example.json` to `config.json`
2. Update the configuration with your Salesforce credentials and settings

### Company Data Source

**Important:** Company information (name, address, VAT number, IBAN, etc.) is now automatically extracted from the Salesforce `c2g__codaCompany__c` object. The following fields are retrieved:

- **Name**: Company name (Latin) - `Name`
- **Name (Cyrillic)**: Company name in Cyrillic - `FF_Name_cyrillic__c`
- **Registration Number**: Company identification number - `SFocus_Company_Identification_Number__c`
- **VAT Number**: Tax registration number - `c2g__VATRegistrationNumber__c`
- **Address**: Street address (Cyrillic) - `F_Address_Cyrillic__c` or `c2g__Street__c`
- **City**: City name (Cyrillic) - `F_City_Cyrillic__c` or `c2g__City__c`
- **Postal Code**: - `c2g__ZipPostCode__c`
- **Country**: - `c2g__Country__c`
- **Region**: State/Province - `c2g__StateProvince__c`
- **Telephone**: - `c2g__Phone__c`
- **Fax**: - `c2g__Fax__c`
- **Email**: Contact email - `c2g__ContactEmail__c`
- **Website**: - `c2g__Website__c`
- **IBAN**: Bank account IBAN - `c2g__BankAccount__r.c2g__IBANNumber__c`

All this data is pulled directly from Salesforce when you run the export, so there's no need to manually maintain it in the config file.

### Authentication Methods

This tool supports two authentication methods:

#### Option 1: OAuth 2.0 (Recommended for SSO)

Best for organizations using SSO (SAML, Google, Microsoft, etc.)

**Setup:**
1. Create a Connected App in Salesforce (see `OAUTH_SETUP.md`)
2. Configure `config.json`:

```json
{
  "salesforce": {
    "auth_method": "oauth",
    "client_id": "your-consumer-key",
    "client_secret": "your-consumer-secret",
    "domain": "login",
    "api_version": "59.0"
  }
}
```

See **`OAUTH_SETUP.md`** for detailed OAuth setup instructions.

#### Option 2: Username/Password (Traditional)

For non-SSO orgs with username/password authentication:

```json
{
  "salesforce": {
    "auth_method": "password",
    "username": "user@company.com",
    "password": "your-password",
    "security_token": "your-security-token",
    "domain": "login",
    "api_version": "59.0"
  }
}
```

**Domain Settings (both methods):**
- Use `"login"` for production orgs
- Use `"test"` for sandbox orgs
- Use your My Domain name if applicable

## Usage

### Basic Usage

```bash
python main.py --start-date 2024-01-01 --end-date 2024-12-31
```

### Filter by Company

To extract data for a specific company only (e.g., Scalefocus AD):

```bash
python main.py --start-date 2024-01-01 --end-date 2024-12-31 --company "Scalefocus AD"
```

This will:
- Filter all journal entries and transactions by the specified company
- Include only GL accounts that are actually used by that company
- Set the company name in the SAF-T XML header

**Available Companies:**
- Scalefocus AD
- Scalefocus DOOEL
- Scalefocus GmbH
- Scalefocus Inc.
- Scalefocus Ltd.
- Scalefocus Turkey
- And others...

### Command Line Options

- `--start-date` (required): Start date for data extraction (YYYY-MM-DD)
- `--end-date` (required): End date for data extraction (YYYY-MM-DD)
- `--company` (optional): Company name to filter data
- `--config` (optional): Path to configuration file (default: config.json)
- `--output` (optional): Output directory (default: output/)
- `--log-level` (optional): Logging level (DEBUG, INFO, WARNING, ERROR)

## Project Structure

- `main.py` - Main entry point
- `src/` - Source code
  - `salesforce/` - Salesforce API integration
  - `transformers/` - Data transformation logic
  - `saft/` - SAF-T XML generation
- `config.json` - Configuration file
- `output/` - Generated SAF-T XML files

## SAF-T Requirements

This implementation follows the Bulgarian SAF-T schema requirements for financial reporting.

## Troubleshooting

### Authentication Errors

**Error: "Invalid username, password, security token"**
- Verify your username and password are correct
- Reset your security token (Setup → Personal Information → Reset My Security Token)
- Check that you have API Enabled permission
- Ensure your IP is in the trusted IP range or you're using the security token

**Error: "SOAP Login operation is not available in API version X"**
- The API version is too high (65.0+)
- Change `api_version` in config.json to `"59.0"`

**Error: "Failed to resolve 'domain.salesforce.com'"**
- Check the `domain` setting in config.json
- Use `"login"` for production, `"test"` for sandbox
- If using My Domain, use only the domain name (not the full URL)

### Data Extraction Issues

- Ensure you have read permission on Certinia objects
- Check that Certinia Finance Cloud is installed in your org
- Verify the object API names match your Certinia version

### Performance

- For large datasets (millions of records), increase `timeout` in config.json
- The Bulk API 2.0 is designed for large volumes
- Monitor job status in Salesforce Setup → Bulk Data Load Jobs
