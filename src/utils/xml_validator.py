from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable

import lxml.etree as ET


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
INVALID_DOC_NAMESPACE = (
    b'xmlns:doc="urn:schemas-OECD:schema-extensions:documentation xml:lang=en"'
)
SANITIZED_DOC_NAMESPACE = (
    b'xmlns:doc="urn:schemas-OECD:schema-extensions:documentation"'
)
SALESFORCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")


def _load_default_schema_path(config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load validation schema path from {config_path}: {exc}") from exc

    configured_path = config.get("validation", {}).get("schema_path")
    if not configured_path:
        raise RuntimeError(
            f"Missing validation.schema_path in {config_path}"
        )

    return Path(configured_path)


DEFAULT_SCHEMA_PATH = _load_default_schema_path()


@dataclass(slots=True)
class ValidationIssue:
    file_path: Path
    status: str
    message: str
    line: int | None = None
    column: int | None = None
    salesforce_record_id: str | None = None
    salesforce_record_address: str | None = None
    salesforce_context: str | None = None


@dataclass(slots=True)
class ValidationReport:
    target_path: Path
    result_path: Path
    checked_files: list[Path]
    issues: list[ValidationIssue]
    invalid_count: int


@dataclass(slots=True)
class ValidationLookup:
    gl_accounts_by_account_id: dict[str, str]
    customers_by_customer_id: dict[str, str]
    suppliers_by_supplier_id: dict[str, str]


def resolve_result_path(target_path: Path, result_xml: str | Path | None) -> Path:
    if result_xml:
        return Path(result_xml)
    if target_path.is_file():
        return target_path.with_name(f"{target_path.stem}_validation_result.xml")
    return target_path / "validation_result.xml"


def load_schema(schema_path: Path) -> ET.XMLSchema:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_bytes = schema_path.read_bytes()
    if INVALID_DOC_NAMESPACE in schema_bytes:
        schema_bytes = schema_bytes.replace(
            INVALID_DOC_NAMESPACE,
            SANITIZED_DOC_NAMESPACE,
            1,
        )

    schema_root = ET.fromstring(schema_bytes, base_url=str(schema_path.resolve()))
    schema_doc = ET.ElementTree(schema_root)
    return ET.XMLSchema(schema_doc)


def resolve_xml_files(target: Path, pattern: str) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(path for path in target.glob(pattern) if path.is_file())
    raise FileNotFoundError(f"Target path not found: {target}")


def _build_schema_issues(xml_path: Path, error_log: Iterable[ET._LogEntry]) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            file_path=xml_path,
            status="INVALID",
            line=error.line,
            column=error.column,
            message=error.message,
        )
        for error in error_log
    ]


def _local_name(element: ET._Element) -> str:
    tag = element.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return str(tag)


def _is_salesforce_id(value: str | None) -> bool:
    return bool(value and SALESFORCE_ID_PATTERN.fullmatch(value.strip()))


def _find_candidate_element(root: ET._Element, line_number: int | None) -> ET._Element | None:
    if line_number is None:
        return None

    candidate = None
    candidate_line = -1
    for element in root.iter():
        source_line = getattr(element, "sourceline", None)
        if source_line is None:
            continue
        if source_line <= line_number and source_line >= candidate_line:
            candidate = element
            candidate_line = source_line
    return candidate


def _build_parent_map(root: ET._Element) -> dict[ET._Element, ET._Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _iter_self_and_ancestors(element: ET._Element | None, parent_map: dict[ET._Element, ET._Element]):
    current = element
    while current is not None:
        yield current
        current = parent_map.get(current)


def _direct_child_text(element: ET._Element, child_name: str) -> str | None:
    for child in element:
        if _local_name(child) == child_name:
            return (child.text or "").strip() or None
    return None


def _build_salesforce_record_address(base_url: str | None, record_id: str | None) -> str | None:
    if not base_url or not record_id:
        return None
    return f"{base_url.rstrip('/')}/{record_id}"


def build_validation_lookup(saft_data: dict[str, Any] | None) -> ValidationLookup:
    if not saft_data:
        return ValidationLookup({}, {}, {})

    master_files = saft_data.get("master_files", {})
    gl_accounts = {
        str(account.get("account_id", "")): str(account.get("source_salesforce_id", ""))
        for account in master_files.get("general_ledger_accounts", [])
        if account.get("account_id") and account.get("source_salesforce_id")
    }
    customers = {
        str(customer.get("customer_id", "")): str(customer.get("source_salesforce_id", ""))
        for customer in master_files.get("customers", [])
        if customer.get("customer_id") and customer.get("source_salesforce_id")
    }
    suppliers = {
        str(supplier.get("supplier_id", "")): str(supplier.get("source_salesforce_id", ""))
        for supplier in master_files.get("suppliers", [])
        if supplier.get("supplier_id") and supplier.get("source_salesforce_id")
    }
    return ValidationLookup(gl_accounts, customers, suppliers)


def _set_issue_salesforce_record(
    issue: ValidationIssue,
    record_id: str | None,
    salesforce_base_url: str | None,
    context: str,
) -> ValidationIssue:
    if not _is_salesforce_id(record_id):
        return issue

    issue.salesforce_record_id = record_id
    issue.salesforce_context = context
    issue.salesforce_record_address = _build_salesforce_record_address(
        salesforce_base_url,
        record_id,
    )
    return issue


def _resolve_issue_from_lookup(
    issue: ValidationIssue,
    candidate: ET._Element,
    parent_map: dict[ET._Element, ET._Element],
    lookup: ValidationLookup,
    salesforce_base_url: str | None,
) -> ValidationIssue:
    candidate_name = _local_name(candidate)
    candidate_text = (candidate.text or "").strip()

    if not candidate_text:
        return issue

    ancestors = list(_iter_self_and_ancestors(candidate, parent_map))
    ancestor_names = {_local_name(element) for element in ancestors}

    if candidate_name == "AccountID":
        if "Account" in ancestor_names:
            return _set_issue_salesforce_record(
                issue,
                lookup.gl_accounts_by_account_id.get(candidate_text),
                salesforce_base_url,
                "Account",
            )

        if "TransactionLine" in ancestor_names or "InvoiceLine" in ancestor_names or "PaymentLine" in ancestor_names:
            return _set_issue_salesforce_record(
                issue,
                lookup.gl_accounts_by_account_id.get(candidate_text),
                salesforce_base_url,
                candidate_name,
            )

        customer_ancestor = next((element for element in ancestors if _local_name(element) == "Customer"), None)
        if customer_ancestor is not None:
            customer_id = _direct_child_text(customer_ancestor, "CustomerID")
            return _set_issue_salesforce_record(
                issue,
                lookup.customers_by_customer_id.get(customer_id or ""),
                salesforce_base_url,
                "Customer",
            )

        supplier_ancestor = next((element for element in ancestors if _local_name(element) == "Supplier"), None)
        if supplier_ancestor is not None:
            supplier_id = _direct_child_text(supplier_ancestor, "SupplierID")
            return _set_issue_salesforce_record(
                issue,
                lookup.suppliers_by_supplier_id.get(supplier_id or ""),
                salesforce_base_url,
                "Supplier",
            )

    if candidate_name == "CustomerID":
        return _set_issue_salesforce_record(
            issue,
            lookup.customers_by_customer_id.get(candidate_text),
            salesforce_base_url,
            "Customer",
        )

    if candidate_name == "SupplierID":
        return _set_issue_salesforce_record(
            issue,
            lookup.suppliers_by_supplier_id.get(candidate_text),
            salesforce_base_url,
            "Supplier",
        )

    return issue


def enrich_issue_with_salesforce_record(
    issue: ValidationIssue,
    document_root: ET._Element,
    parent_map: dict[ET._Element, ET._Element],
    salesforce_base_url: str | None,
    lookup: ValidationLookup,
) -> ValidationIssue:
    if issue.status != "INVALID":
        return issue

    candidate = _find_candidate_element(document_root, issue.line)
    if candidate is None:
        return issue

    for element in _iter_self_and_ancestors(candidate, parent_map):
        for child_name in ("SourceDocumentID", "SystemID"):
            record_id = _direct_child_text(element, child_name)
            if _is_salesforce_id(record_id):
                return _set_issue_salesforce_record(
                    issue,
                    record_id,
                    salesforce_base_url,
                    _local_name(element),
                )

    return _resolve_issue_from_lookup(issue, candidate, parent_map, lookup, salesforce_base_url)


def build_result_messages(issues: list[ValidationIssue]) -> list[str]:
    timestamp = datetime.now().astimezone().strftime("%a %b %d %H:%M:%S %Z %Y")
    messages = []
    error_number = 1

    for issue in issues:
        if issue.status == "VALID":
            continue

        location = ""
        if issue.line is not None and issue.column is not None:
            location = f"Line {issue.line}, Column {issue.column}: "
        salesforce_suffix = ""
        if issue.salesforce_record_address:
            salesforce_suffix = (
                f" | Salesforce record: {issue.salesforce_record_address}"
            )
        messages.append(
            f"{timestamp} - XML VALIDATION ERROR: Error {error_number}: "
            f"{issue.file_path.name}: {location}{issue.message}{salesforce_suffix}"
        )
        error_number += 1

    return messages


def write_result_xml(result_path: Path, messages: list[str]) -> None:
    result_root = ET.Element("errsaft")
    for index, message in enumerate(messages, start=1):
        error_elem = ET.SubElement(result_root, "error")
        err_number = ET.SubElement(error_elem, "err_number")
        err_number.text = str(index)
        err_descr = ET.SubElement(error_elem, "err_descr")
        err_descr.text = message

    result_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(result_root)
    tree.write(
        str(result_path),
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
        pretty_print=True,
    )


def create_single_issue(
    target_path: Path,
    status: str,
    detail: str,
    *,
    line: int | None = None,
    column: int | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        file_path=target_path,
        status=status,
        message=detail,
        line=line,
        column=column,
    )


def validate_file(xml_path: Path, schema: ET.XMLSchema) -> tuple[bool, list[ValidationIssue]]:
    parser = ET.XMLParser(remove_blank_text=False)
    document = ET.parse(str(xml_path), parser)
    is_valid = schema.validate(document)
    if is_valid:
        return True, [ValidationIssue(file_path=xml_path, status="VALID", message="XML is valid against the schema.")]

    return False, _build_schema_issues(xml_path, schema.error_log)


def validate_target(
    target: str | Path,
    *,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    pattern: str = "*.xml",
    result_xml: str | Path | None = None,
    salesforce_base_url: str | None = None,
    saft_data: dict[str, Any] | None = None,
) -> ValidationReport:
    target_path = Path(target)
    schema_path = Path(schema_path)
    result_path = resolve_result_path(target_path, result_xml)
    lookup = build_validation_lookup(saft_data)

    try:
        schema = load_schema(schema_path)
        xml_files = resolve_xml_files(target_path, pattern)
    except (OSError, ET.XMLSyntaxError, ET.XMLSchemaParseError) as exc:
        issues = [create_single_issue(target_path, "ERROR", str(exc))]
        write_result_xml(result_path, build_result_messages(issues))
        return ValidationReport(target_path, result_path, [], issues, 1)

    if not xml_files:
        issues = [
            create_single_issue(
                target_path,
                "ERROR",
                f"No XML files found in {target_path} matching {pattern}",
            )
        ]
        write_result_xml(result_path, build_result_messages(issues))
        return ValidationReport(target_path, result_path, [], issues, 1)

    invalid_count = 0
    issues: list[ValidationIssue] = []

    for xml_file in xml_files:
        try:
            parser = ET.XMLParser(remove_blank_text=False)
            document = ET.parse(str(xml_file), parser)
            document_root = document.getroot()
            is_valid = schema.validate(document)
            if is_valid:
                file_issues = [
                    ValidationIssue(
                        file_path=xml_file,
                        status="VALID",
                        message="XML is valid against the schema.",
                    )
                ]
            else:
                parent_map = _build_parent_map(document_root)
                file_issues = [
                    enrich_issue_with_salesforce_record(
                        validation_issue,
                        document_root,
                        parent_map,
                        salesforce_base_url,
                        lookup,
                    )
                    for validation_issue in _build_schema_issues(xml_file, schema.error_log)
                ]
        except (OSError, ET.XMLSyntaxError) as exc:
            invalid_count += 1
            issues.append(create_single_issue(xml_file, "ERROR", f"Parse error: {exc}"))
            continue

        issues.extend(file_issues)
        if not is_valid:
            invalid_count += 1

    write_result_xml(result_path, build_result_messages(issues))
    return ValidationReport(target_path, result_path, xml_files, issues, invalid_count)