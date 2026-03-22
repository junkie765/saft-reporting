# Copilot Instructions for SAF-T Reporting (Bulgaria)

## Project Overview
- **Purpose:** Extract financial data from Salesforce (Certinia Finance Cloud) and transform it into Bulgarian SAF-T XML format.
- **Main entry:** `main.py` orchestrates extraction, transformation, and export.
- **Core modules:**
  - `src/salesforce/`: Salesforce API integration (OAuth 2.0 PKCE, Bulk API 2.0, REST client)
  - `src/transformers/`: Data transformation from Certinia to SAF-T schema
  - `src/saft/`: SAF-T XML generation logic
  - `src/ui/`: Minimal UI logic (e.g., `saft_ui.py` for interactive or visual operations)
  - `src/utils/`: Logging, Excel export, helpers

## Data Flow
1. **Config:** Reads `config.json` for Salesforce OAuth credentials and settings.
2. **Auth:** Connects to Salesforce using OAuth 2.0 PKCE (SSO only; username/password is not supported).
3. **Extraction:** Uses Bulk API 2.0 to pull large datasets from Certinia objects.
4. **Transformation:** Maps Salesforce/Certinia fields to Bulgarian SAF-T schema (see `src/transformers/certinia_transformer.py`).
5. **Export:** Generates SAF-T XML files in `output/`.

## Key Patterns & Conventions
- **Company data** is auto-extracted from Salesforce (`c2g__codaCompany__c`), not manually maintained.
- **Field mapping** for company and transaction data is explicit in transformer modules.
- **User input:** All main operations use the UI (`src/ui/saft_ui.py`) for parameter selection and input, which passes selections to the script. CLI flags are available for automation or advanced use.
- **UTF-8 encoding** is enforced for Cyrillic support.
- **Logging:** Controlled via `--log-level` and `src/utils/logger.py`.

## Developer Workflows
- **Install dependencies:** `pip install -r requirements.txt`
- **Run extraction:**
  ```pwsh
  python main.py
  ```
- **Test scripts:** Located in `archive/` and `tests/` (run with `python test_*.py` or use a test runner)
- **Debugging:** Use increased log level (`--log-level DEBUG`) and inspect logs in `logs/`.

## Integration Points
- **Salesforce:** Bulk API 2.0, OAuth 2.0 PKCE, Certinia objects
- **Output:** SAF-T XML files in `output/`
- **Config:** `config.json` (see `README.md` for details)

## Notable Files
- `main.py`: CLI entry, orchestrates workflow
- `config.json`: Configuration file
- `requirements.txt`: Python dependencies
- `output/`: Generated SAF-T XML files
- `logs/`: Log files
- `archive/`: Diagnostic and test scripts
- `scripts/`: Data analysis and validation scripts
- `Supporting_docs/`: Field definitions, schema, and reference docs
- `src/salesforce/auth.py`: Handles authentication
- `src/salesforce/rest_client.py`: Salesforce REST/Bulk API client
- `src/transformers/certinia_transformer.py`: Data mapping logic
- `src/saft/saft_generator.py`: XML generation
- `src/ui/saft_ui.py`: UI logic for interactive/visual operations
- `src/utils/logger.py`: Logging setup
- `src/utils/excel_exporter.py`: Excel export logic
- `README.md`: Setup, config, and usage details

## Example CLI Usage
```pwsh
python main.py
```

## Tips for AI Agents
- Always reference `README.md` for up-to-date config and workflow details.
- When adding new Certinia fields, update transformer logic and document mappings.
- For new company data, ensure extraction logic in Salesforce modules is updated.
- Use Bulk API for large data volumes; monitor for timeouts and pagination.
- Keep output files in `output/` and logs in `logs/`.

---
_Review and update this file as project structure or workflows evolve._
