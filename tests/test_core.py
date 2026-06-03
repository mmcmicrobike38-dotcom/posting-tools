from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from core.accounts import (
    accounts_ledger_deduction,
    append_line_break,
    build_fully_paid_cash_export,
    find_section_row,
    prepare_accounts_preview,
    prepare_daily_collection_updates,
    prepare_ibp_source_branch_updates,
    prepare_sheet_updates,
    subtract_numeric,
    sum_numeric,
)
from core.ai_resolver import build_ai_resolver_context, resolve_posting_with_gemini
from core.audit import write_audit_log
from core.branch_folder_lookup import build_branch_index, detect_branch_id_from_filename, extract_drive_folder_id, scan_branch_folder, scan_branch_folder_metadata
from core.classifier import classify_accounts, classify_daily
from core.concurrency import BranchLockError, LocalCsvDuplicateAuditStore, branch_lock_key
from core.daily_report import daily_tab_name, find_blank_daily_rows, prepare_daily_preview, prepare_daily_sheet_updates
from core.google_sheets import (
    AUTH_MODE_SERVICE_ACCOUNT,
    AUTH_MODE_USER_OAUTH,
    create_google_clients,
    extract_spreadsheet_id,
    fetch_worksheet_rows,
    google_actor_email,
    oauth_token_file_is_encrypted,
    protect_oauth_token_json,
    post_to_google_sheet,
    unprotect_oauth_token_json,
    validate_oauth_client_info,
    validate_service_account_info,
)
from core.ibp_resolver import (
    annotate_ibp_rows,
    build_ibp_accounts_entry,
    build_ibp_accounts_line,
    is_ibp_transaction,
    parse_ibp_reference,
    resolve_ibp_customer,
)
from core.other_payment import (
    annotate_other_payment_rows,
    build_other_payment_accounts_entry,
    is_other_payment_transaction,
)
from core.parser import actual_collection, generate_transaction_key, parse_account, parse_amount, parse_date, parse_reference
from core.receipt import (
    build_series_index,
    find_receipt_blocks,
    prepare_receipt_preview,
    prepare_receipt_updates,
    receipt_block_end,
    receipt_block_start,
    skipped_receipt_series,
)
from core.scr_vs_br import (
    _latest_or_before_row,
    append_or_normally,
    append_or_with_breakline,
    assign_scr_blocks,
    build_receipt_blocks,
    contiguous_or_ranges,
    get_or_end,
    get_or_start,
    is_continueable_or,
    parse_or_range,
    prepare_scr_vs_br_updates,
)
from core.validation import can_confirm_post, can_swipe_to_post, calculate_summary, parse_and_validate_simsoft, reconciliation_variance
from core.stores import LocalBranchIndexStore, LocalDuplicateStore, LocalIBPLookupCacheStore
from python_backend.models.app_state import AppState
from python_backend.services.workflow_service import SimsoftWorkflowService, accounts_layout_preview, daily_tab_aliases, daily_tab_for_parsed_rows, friendly_google_error, passed_transaction_keys, scr_layout_preview, sync_parsed_status_from_accounts_preview
from core.audit import load_duplicate_history


HEADERS = ["ACCOUNT", "DATE", "REF", "REB", "CASH", "DP", "CM", "CM TO M", "M", "PENALTY", "OTHERS", "REPO", "OUTSTANDING BALANCE", "SIMSOFT LEDGER BALANCE"]
HEADERS_WITH_STATUS = HEADERS + ["STATUS", "DATE FULLY PAID"]
HEADERS_WITH_CODE_STATUS = ["ACCOUNT", "CODE", "DATE", "REF", "REB", "CASH", "DP", "CM", "CM TO M", "M", "PENALTY", "OTHERS", "REPO", "OUTSTANDING BALANCE", "SIMSOFT LEDGER BALANCE", "STATUS", "DATE FULLY PAID"]
SHEET_ROWS = [
    ["title"],
    ["notes"],
    HEADERS,
    ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "2026-01-01", "OLDREF", "10.00", "", "", "", "", "100.00", "5.00", "", "", "850.00", "900.00"],
]


def simsoft_row(**overrides):
    row = {
        "Account Name": "MMC042-01167R / RICHIELLE ABEJUELLA DARIA",
        "Date": "2026-05-02",
        "Code": "",
        "Reference": "19045 - (21/24 MI P)",
        "Interest": "1001",
        "Amount": "1999",
        "Rebate": "2.00",
        "Total": "",
        "Balance": "800.00",
        "IntPaid": "",
        "VAT": "",
        "Advance": "",
        "Penalty": "",
    }
    row.update(overrides)
    return row


def test_extract_spreadsheet_id_from_url_and_raw_id():
    assert extract_spreadsheet_id("https://docs.google.com/spreadsheets/d/abc-123_DEF/edit") == "abc-123_DEF"
    assert extract_spreadsheet_id("abc12345678901234567890") == "abc12345678901234567890"


def test_ai_resolver_is_disabled_without_gemini_key(monkeypatch):
    monkeypatch.delenv("SIMSOFT_ENABLE_AI_RESOLVER", raising=False)
    monkeypatch.delenv("SIMSOFT_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    context = build_ai_resolver_context(
        parsed_df=pd.DataFrame([{"Transaction Key": "k1", "OR Number": "1001"}]),
        accounts_preview_df=pd.DataFrame([{"Status": "ERROR", "Issue": "Account not found in ACCOUNTS", "Transaction Key": "k1"}]),
        receipt_preview_df=pd.DataFrame(),
        daily_preview_df=pd.DataFrame(),
        scr_preview_df=pd.DataFrame(),
        accounts_rows=SHEET_ROWS,
        accounts_headers=HEADERS,
        receipt_rows=[],
        receipt_headers=[],
        daily_rows=[],
        scr_rows=[],
        scr_updates=[],
        active_receipt_tab="RECEIPT",
        active_daily_tab="1-31",
        target_branch_id="MMC042",
        target_branch_name="Test Branch",
        errors=["Account not found in ACCOUNTS"],
    )

    report = resolve_posting_with_gemini(context)

    assert report["enabled"] is False
    assert report["status"] == "disabled"
    assert report["suggestions"] == []


def test_ai_resolver_requires_explicit_opt_in_even_with_key(monkeypatch):
    monkeypatch.delenv("SIMSOFT_ENABLE_AI_RESOLVER", raising=False)
    monkeypatch.setenv("SIMSOFT_GEMINI_API_KEY", "test-key")

    report = resolve_posting_with_gemini({"errors": ["Account not found in ACCOUNTS"]})

    assert report["enabled"] is False
    assert report["status"] == "disabled"


def test_ai_resolver_rejects_unsafe_model_name(monkeypatch):
    monkeypatch.setenv("SIMSOFT_ENABLE_AI_RESOLVER", "1")
    monkeypatch.setenv("SIMSOFT_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("SIMSOFT_GEMINI_MODEL", "../bad?x=1")

    report = resolve_posting_with_gemini({"errors": ["Account not found in ACCOUNTS"]})

    assert report["status"] == "error"
    assert "Invalid Gemini model name" in report["error"]


def test_ai_resolver_context_serializes_nested_decimals():
    import json

    context = build_ai_resolver_context(
        parsed_df=pd.DataFrame([{"Status": "ERROR", "Amount": Decimal("10.50"), "Transaction Key": "k1"}]),
        accounts_preview_df=pd.DataFrame([{"Status": "ERROR", "Issue": "Bad amount", "Amount": Decimal("10.50")}]),
        receipt_preview_df=pd.DataFrame(),
        daily_preview_df=pd.DataFrame(),
        scr_preview_df=pd.DataFrame(),
        accounts_rows=[["ACCOUNT", Decimal("10.50")]],
        accounts_headers=HEADERS,
        receipt_rows=[],
        receipt_headers=[],
        daily_rows=[],
        scr_rows=[],
        scr_updates=[{"row": 1, "col": 2, "value": Decimal("10.50")}],
        active_receipt_tab="RECEIPT",
        active_daily_tab="1-31",
        target_branch_id="MMC042",
        target_branch_name="Test Branch",
        errors=["Bad amount"],
    )

    encoded = json.dumps(context)

    assert "10.50" in encoded


def test_parse_amount_handles_currency_commas_and_parentheses():
    assert parse_amount("R 1,234.50") == Decimal("1234.50")
    assert parse_amount("(45.10)") == Decimal("-45.10")


def test_parse_date_outputs_iso_date():
    assert parse_date("2026-05-07") == "2026-05-07"
    assert parse_date(pd.Timestamp("2026-05-07")) == "2026-05-07"


def test_account_parsing():
    assert parse_account("MMC042-01167R / RICHIELLE ABEJUELLA DARIA") == ("MMC042-01167R", "RICHIELLE ABEJUELLA DARIA")


def test_reference_parsing():
    assert parse_reference("18947 - (19-20/24 MI P)") == ("18947", "(19-20/24 MI P)")
    with pytest.raises(ValueError):
        parse_reference("NO OR")


def test_transaction_type_classification():
    assert classify_accounts("x CM TO M y") == "CM TO M"
    assert classify_accounts("x CM y") == "CM"
    assert classify_accounts("x CASH y") == "CASH"
    assert classify_accounts("19045 - (DP/MI)") == "M"
    assert classify_accounts("x MIP y") == "M"
    assert classify_accounts("24/25") == "M"
    assert classify_accounts("19-20/24") == "M"
    assert classify_accounts("19045 - (NO AMOUNT)") == "NO AMOUNT"
    assert classify_daily("(CASH)") == "CASH"
    assert classify_daily("(DP/MI)") == "MI"
    assert classify_daily("(21/24 MI P)") == "MI"
    assert classify_daily("(MIP)") == "MI"
    assert classify_daily("(24/25)") == "MI"


def test_other_payment_detection_and_accounts_line():
    assert is_other_payment_transaction("OTHER PAYMENTS / MMC075-SAN CARLOS")
    assert is_other_payment_transaction("OTHER PAYMENT / MMC075-SAN CARLOS")
    assert not is_other_payment_transaction("IBP PAYMENTS / MMC075 - SAN CARLOS")
    assert (
        build_other_payment_accounts_entry("5477", "MMC075-SAN CARLOS", Decimal("415.00"))
        == "5477 - OTHER PAYMENT /MMC075-SAN CARLOS        (415.00)"
    )


def test_other_payment_annotation_does_not_need_lookup():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "415",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    annotated = annotate_other_payment_rows(parsed)
    assert annotated.iloc[0]["Status"] == "PASSED"
    assert annotated.iloc[0]["is_other_payment"]
    assert not annotated.iloc[0].get("is_ibp", False)
    assert annotated.iloc[0]["other_payment_accounts_entry"] == "5477 - OTHER PAYMENT /MMC075-SAN CARLOS        (415.00)"


def test_is_ibp_transaction_before_normal_classification():
    assert is_ibp_transaction("IBP PAYMENTS / MMC075 - SAN CARLOS", "5083 - (MMC038-02607)")
    assert is_ibp_transaction("Normal Account", "5083 - (MMC038-02607)")
    assert parse_ibp_reference("5083 - (MMC038-02607)")["ibp_account_no"] == "MMC038-02607"


def test_extract_drive_folder_id_and_branch_id_from_filename():
    assert extract_drive_folder_id("https://drive.google.com/drive/folders/abc123") == "abc123"
    assert detect_branch_id_from_filename("MMC042 - BAYAMBANG REALTIME 2026") == "MMC042"


def test_build_branch_index_detects_branches():
    files = [
        {"id": "sheet1", "name": "MMC038 - POZORRUBIO REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet", "modifiedTime": "2026-01-01T00:00:00Z"},
        {"id": "sheet2", "name": "MMC042 - BAYAMBANG REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet", "modifiedTime": "2026-01-02T00:00:00Z"},
    ]
    index = build_branch_index(files)
    assert index["MMC038"]["branch_id"] == "MMC038"
    assert index["MMC038"]["branch_name"] == "POZORRUBIO"
    assert index["MMC042"]["spreadsheet_id"] == "sheet2"
    assert index["MMC042"]["modified_time"] == "2026-01-02T00:00:00Z"


def test_build_branch_index_marks_duplicate_branch_ids():
    index = build_branch_index(
        [
            {"id": "sheet1", "name": "MMC038 - POZORRUBIO REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet"},
            {"id": "sheet2", "name": "MMC038 - POZORRUBIO COPY", "mimeType": "application/vnd.google-apps.spreadsheet"},
        ]
    )

    assert index["MMC038"]["status"] == "MULTIPLE_MATCHES"
    assert index["MMC038"]["matching_file_names"] == ["MMC038 - POZORRUBIO REALTIME 2026", "MMC038 - POZORRUBIO COPY"]


def test_build_ibp_accounts_line():
    assert build_ibp_accounts_line("5083", "MMC038-02607 / REYNALDO MOLANO POQUIZ") == "5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ"
    assert (
        build_ibp_accounts_entry("5083", "MMC038-02607 / REYNALDO MOLANO POQUIZ", Decimal("1797"))
        == "5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ     (1,797.00)"
    )


def test_ibp_missing_branch_sheet_validation():
    result = resolve_ibp_customer("MMC038-02607", {}, {"client_email": "test@example.com"})
    assert result["status"] == "ERROR"
    assert "Branch sheet not found for MMC038" in result["issue"]


def test_ibp_duplicate_branch_sheet_validation():
    result = resolve_ibp_customer(
        "MMC038-02607",
        {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123", "status": "MULTIPLE_MATCHES"}},
        {"client_email": "test@example.com"},
    )
    assert result["status"] == "ERROR"
    assert "Multiple branch sheets found for MMC038" in result["issue"]


def test_ibp_missing_customer_validation(monkeypatch):
    branch_index = {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123"}}

    def fake_fetch_rows(sheet_url, worksheet_name, service_account_info):
        return object(), [["title"], ["notes"], ["ACCOUNT"]]

    monkeypatch.setattr("core.ibp_resolver.fetch_worksheet_rows", fake_fetch_rows)
    result = resolve_ibp_customer("MMC038-02607", branch_index, {"client_email": "test@example.com"})
    assert result["status"] == "NEEDS REVIEW"
    assert "IBP customer account not found" in result["issue"]


def test_ibp_resolution_uses_branch_sheet_account(monkeypatch):
    branch_index = {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123"}}

    def fake_fetch_rows(sheet_url, worksheet_name, service_account_info):
        return object(), [
            ["title"],
            ["notes"],
            ["ACCOUNT"],
            ["MMC038-02607 / REYNALDO MOLANO POQUIZ"],
        ]

    monkeypatch.setattr("core.ibp_resolver.fetch_worksheet_rows", fake_fetch_rows)
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                        "Reference": "5083 - (MMC038-02607)",
                        "Amount": "1797",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    annotated = annotate_ibp_rows(parsed, branch_index, {"client_email": "test@example.com"})
    assert annotated.iloc[0]["Status"] == "PASSED"
    assert annotated.iloc[0]["ibp_source_branch_id"] == "MMC038"
    assert annotated.iloc[0]["ibp_resolved_customer"] == "MMC038-02607 / REYNALDO MOLANO POQUIZ"
    assert annotated.iloc[0]["ibp_accounts_entry"] == "5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ     (1,797.00)"


def test_ibp_resolution_caches_same_source_account_lookup(monkeypatch):
    branch_index = {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123"}}
    call_count = {"count": 0}

    def fake_fetch_rows(sheet_url, worksheet_name, service_account_info):
        call_count["count"] += 1
        return object(), [
            ["title"],
            ["notes"],
            ["ACCOUNT"],
            ["MMC038-02607 / REYNALDO MOLANO POQUIZ"],
        ]

    monkeypatch.setattr("core.ibp_resolver.fetch_worksheet_rows", fake_fetch_rows)
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                        "Reference": "5083 - (MMC038-02607)",
                        "Amount": "1797",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
                simsoft_row(
                    **{
                        "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                        "Reference": "5084 - (MMC038-02607)",
                        "Amount": "1797",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    annotated = annotate_ibp_rows(parsed, branch_index, {"client_email": "test@example.com"})
    assert list(annotated["Status"]) == ["PASSED", "PASSED"]
    assert call_count["count"] == 1


def test_transaction_key_generation_is_stable_for_equivalent_values():
    first = generate_transaction_key(simsoft_row(Amount="100"))
    second = generate_transaction_key(simsoft_row(Amount="100.00"))
    assert first == second


def test_duplicate_detection_from_history():
    key = generate_transaction_key(
        {
            "Account Name": "ALPHA",
            "Date": "2026-05-07",
            "Reference": "REF123",
            "Interest": "1.50",
            "Amount": "100.00",
            "Rebate": "2.00",
        }
    )
    assert key in load_duplicate_history("tests/fixtures_duplicate_history.csv")


def test_daily_tab_name_detection():
    assert daily_tab_name(date(2026, 2, 1)) == "1-28"
    assert daily_tab_name(date(2024, 2, 1)) == "1-29"
    assert daily_tab_name(date(2026, 4, 1)) == "1-30"
    assert daily_tab_name(date(2026, 5, 1)) == "1-31"


def test_app_daily_tab_detection_from_parsed_rows():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Date="2026-04-05")]), set())
    tab_name, errors = daily_tab_for_parsed_rows(parsed)
    assert errors == []
    assert tab_name == "1-30"

    mixed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(Date="2026-04-05"), simsoft_row(Date="2026-05-05", Reference="19046 - (22/24 MI P)")]),
        set(),
    )
    _, mixed_errors = daily_tab_for_parsed_rows(mixed)
    assert "multiple months" in mixed_errors[0]


def test_daily_tab_aliases_include_dash_variants():
    assert daily_tab_aliases("1-31") == ["1-31", "1–31", "1—31"]


def test_friendly_google_error_prioritizes_missing_tab_over_api_url():
    class WorksheetNotFound(Exception):
        pass

    message = "Worksheet 1-31 not found while calling https://sheets.googleapis.com"
    assert friendly_google_error(WorksheetNotFound(message), "svc@example.com", "sheet", "1-31") == (
        "The tab named 1-31 was not found. Check the spreadsheet tab name."
    )


def test_friendly_google_error_does_not_treat_api_url_as_disabled():
    message = "APIError: [404]: Requested entity was not found at https://sheets.googleapis.com"
    assert friendly_google_error(Exception(message), "svc@example.com", "sheet", "1-31") == message


def test_friendly_google_error_for_quota_is_actionable():
    message = "APIError: [429]: Quota exceeded for quota metric 'Read requests'"
    assert "Refresh Google Sheet Data" in friendly_google_error(Exception(message), "svc@example.com", "sheet", "ACCOUNTS")


def test_actual_collection_amount_plus_interest():
    assert actual_collection("1968", "198") == Decimal("2166.00")


def test_parse_validate_status_passed_duplicate_and_error():
    rows = [simsoft_row(), simsoft_row(Reference="19046 - (22/24 MI P)"), simsoft_row(**{"Account Name": ""})]
    preview, setup_errors = parse_and_validate_simsoft(pd.DataFrame(rows), set())
    assert setup_errors == []
    assert list(preview["Status"]) == ["PASSED", "PASSED", "ERROR"]

    duplicate_key = generate_transaction_key(simsoft_row())
    duplicate_preview, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row()]), {duplicate_key})
    assert duplicate_preview.iloc[0]["Status"] == "DUPLICATE"


def test_parse_validate_skips_blank_summary_rows():
    rows = [simsoft_row(), simsoft_row(**{"Account Name": "", "Date": "", "Reference": "", "Amount": "15146.00"})]
    preview, setup_errors = parse_and_validate_simsoft(pd.DataFrame(rows), set())
    assert setup_errors == []
    assert len(preview) == 1
    assert preview.iloc[0]["Status"] == "PASSED"


def test_parse_validate_skips_rows_with_only_optional_fields():
    rows = [simsoft_row(), {"Account Name": "", "Date": "2025-12-01", "Reference": "", "Amount": "", "Interest": "", "Rebate": "", "Balance": ""}]
    preview, setup_errors = parse_and_validate_simsoft(pd.DataFrame(rows), set())
    assert setup_errors == []
    assert len(preview) == 1
    assert preview.iloc[0]["Status"] == "PASSED"


def test_parse_validate_accepts_blank_optional_numeric_fields():
    row = simsoft_row(Interest="", Rebate="", Balance="")
    preview, setup_errors = parse_and_validate_simsoft(pd.DataFrame([row]), set())
    assert setup_errors == []
    assert preview.iloc[0]["Status"] == "PASSED"
    assert preview.iloc[0]["Interest"] == Decimal("0.00")
    assert preview.iloc[0]["Rebate"] == Decimal("0.00")
    assert preview.iloc[0]["Balance"] == Decimal("0.00")
    assert preview.iloc[0]["Actual Collection"] == Decimal("1999.00")


def test_parse_validate_keeps_simsoft_code_for_copy_box():
    preview, setup_errors = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Code="CODE-123")]), set())
    assert setup_errors == []
    assert preview.iloc[0]["Code"] == "CODE-123"


def test_summary_calculation_counts_and_totals():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(), simsoft_row(Reference="19046 - (22/24 MI P)", Amount="50", Interest="10")]),
        set(),
    )
    summary = calculate_summary(parsed)
    assert summary["Total Rows"] == 2
    assert summary["Passed Rows"] == 2
    assert summary["Amount Total"] == Decimal("2049.00")
    assert summary["Interest Total"] == Decimal("1011.00")
    assert summary["Rebate Total"] == Decimal("4.00")
    assert summary["Actual Collection Total"] == Decimal("3060.00")


def test_accounts_line_break_append_logic():
    assert append_line_break("", "new") == "new"
    assert append_line_break("old", "new") == "old\nnew"


def test_accounts_numeric_summing_logic():
    assert sum_numeric("10.25", "2.75") == Decimal("13.00")
    assert sum_numeric("", "2.75") == Decimal("2.75")
    assert sum_numeric("-", "2.75") == Decimal("2.75")
    assert subtract_numeric("850.00", "1999.00") == Decimal("-1149.00")
    assert subtract_numeric("-", "2.75") == Decimal("-2.75")


def test_accounts_ledger_deduction_adds_only_dp_or_mi_and_rebate():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Amount="1999", Rebate="2", Interest="1001")]), set())
    mi_row = parsed.iloc[0].copy()
    mi_row["Amount Column"] = "M"
    dp_row = parsed.iloc[0].copy()
    dp_row["Amount Column"] = "DP"
    cash_row = parsed.iloc[0].copy()
    cash_row["Amount Column"] = "CASH"
    assert accounts_ledger_deduction(mi_row) == Decimal("2001.00")
    assert accounts_ledger_deduction(dp_row) == Decimal("2001.00")
    assert accounts_ledger_deduction(cash_row) == Decimal("2001.00")


def test_accounts_updates_append_sum_and_replace_balance():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row()]), set())
    accounts_preview, errors = prepare_accounts_preview(parsed, SHEET_ROWS, HEADERS, 3)
    assert errors == []
    updates = prepare_sheet_updates(accounts_preview, SHEET_ROWS, HEADERS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[2] == "2026-01-01\n2-May-26"
    assert values_by_col[3] == "OLDREF\n19045 - (21/24 MI P)"
    assert values_by_col[4] == "12.00"
    assert values_by_col[9] == "=100+1999"
    assert values_by_col[10] == "=5+1001"
    assert values_by_col[14] == "-1151.00"


def test_accounts_dp_mi_particular_posts_to_mi_column():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Reference="19045 - (DP/MI)", Amount="1999", Interest="1001")]), set())
    accounts_preview, errors = prepare_accounts_preview(parsed, SHEET_ROWS, HEADERS, 3)
    assert errors == []
    assert accounts_preview.iloc[0]["Amount Column"] == "M"
    updates = prepare_sheet_updates(accounts_preview, SHEET_ROWS, HEADERS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[6] == ""
    assert values_by_col[9] == "=100+1999"


def test_accounts_same_account_same_date_writes_date_once():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(**{"Account Name": "MMC075-00236 / RUSTYTORIO SERGUINA", "Date": "2025-12-01", "Reference": "5081 - (31-32/36 MI)", "Amount": "10193", "Interest": "93"}),
                simsoft_row(**{"Account Name": "MMC075-00236 / RUSTYTORIO SERGUINA", "Date": "2025-12-01", "Reference": "5082 - (32/36 MI)", "Amount": "0", "Interest": "93"}),
            ]
        ),
        set(),
    )
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC075-00236 / RUSTYTORIO SERGUINA", "", "", "", "", "", "", "", "", "", "", "", "19084.00", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []

    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[2] == "1-Dec-25"
    assert values_by_col[3] == "5081 - (31-32/36 MI)\n5082 - (32/36 MI)"
    assert values_by_col[9] == "=10193"
    assert values_by_col[10] == "=93+93"


def test_accounts_zero_rebate_leaves_reb_blank():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Rebate="0")]), set())
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "", "", "-", "", "", "", "", "", "", "", "", "850.00", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []

    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[4] == ""


def test_accounts_no_amount_column_leaves_amount_buckets_blank():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Reference="19045 - (NO AMOUNT)", Amount="1999", Interest="1001")]), set())
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "", "", "", "", "", "", "", "", "", "", "", "850.00", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "PASSED"
    assert accounts_preview.iloc[0]["Amount Column"] == ""

    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[5] == ""
    assert values_by_col[6] == ""
    assert values_by_col[7] == ""
    assert values_by_col[8] == ""
    assert values_by_col[9] == ""
    assert values_by_col[10] == "=1001"


def test_accounts_zero_balance_installment_marks_fully_paid():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Amount="1999", Rebate="2")]), set())
    rows = [
        ["title"],
        ["notes"],
        HEADERS_WITH_STATUS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "", "", "", "", "", "", "", "", "", "", "", "2001.00", "", "INSTALLMENT", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS_WITH_STATUS, 3)
    assert errors == []

    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS_WITH_STATUS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[14] == "0.00"
    assert values_by_col[15] == "FULLY PAID"
    assert values_by_col[16] == "2-May-26"


def test_accounts_cash_zero_balance_does_not_mark_fully_paid():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Reference="19045 - (CASH)", Amount="850", Interest="0", Rebate="0")]), set())
    rows = [
        ["title"],
        ["notes"],
        HEADERS_WITH_STATUS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "", "", "", "", "", "", "", "", "", "", "", "850.00", "", "INSTALLMENT", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS_WITH_STATUS, 3)
    assert errors == []

    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS_WITH_STATUS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[14] == "0.00"
    assert values_by_col[15] == "INSTALLMENT"
    assert values_by_col[16] == ""


def test_fully_paid_cash_export_lists_account_and_code():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Code="SIMSOFT-FP-CODE", Amount="1999", Rebate="2"),
                simsoft_row(Code="SIMSOFT-CASH-CODE", Reference="19046 - (CASH)", Amount="850", Interest="0", Rebate="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["title"],
        ["notes"],
        HEADERS_WITH_CODE_STATUS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "SHEET-CODE", "", "", "", "", "", "", "", "", "", "", "", "2001.00", "", "INSTALLMENT", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS_WITH_CODE_STATUS, 3)
    assert errors == []

    export_df = build_fully_paid_cash_export(accounts_preview, rows, HEADERS_WITH_CODE_STATUS)

    assert export_df.to_dict("records") == [
        {"Account": "MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "Code": "SHEET-CODE", "Type": "FULLY PAID"},
        {"Account": "MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "Code": "SHEET-CODE", "Type": "CASH"},
    ]


def test_fully_paid_cash_export_keeps_fully_paid_after_post_refresh():
    preview = pd.DataFrame(
        [
            {
                "Account Name": "MMC042-01167R / RICHIELLE ABEJUELLA DARIA",
                "Target Row": 4,
                "Amount Column": "M",
                "Amount": Decimal("1999.00"),
                "Rebate": Decimal("2.00"),
                "Status": "DUPLICATE",
                "Transaction Key": "already-posted",
            }
        ]
    )
    rows = [
        ["title"],
        ["notes"],
        HEADERS_WITH_CODE_STATUS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "SHEET-CODE", "", "", "", "", "", "", "", "", "", "", "", "0.00", "", "FULLY PAID", "2-May-26"],
    ]

    export_df = build_fully_paid_cash_export(preview, rows, HEADERS_WITH_CODE_STATUS)

    assert export_df.to_dict("records") == [
        {"Account": "MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "Code": "SHEET-CODE", "Type": "FULLY PAID"},
    ]


def test_accounts_ibp_updates_section_m_column_only():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5083 - (MMC038-02607)",
                "OR Number": "5083",
                "Particulars": "(MMC038-02607)",
                "Amount": Decimal("1797.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("1797.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key",
                "is_ibp": True,
                "ibp_resolved_customer": "MMC038-02607 / REYNALDO MOLANO POQUIZ",
                "ibp_accounts_entry": "5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ     (1,797.00)",
            }
        ]
    )
    rows = SHEET_ROWS + [["IBP TO OTHER BRANCH", "", "", "", "", "-"], ["", "", "", "", "", ""]]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []
    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert updates == [
        {"row": 6, "col": 1, "value": "5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ"},
        {"row": 6, "col": 6, "value": "(1,797.00)"},
    ]


def test_accounts_ibp_section_can_be_outside_account_column():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5083 - (MMC038-02607)",
                "OR Number": "5083",
                "Particulars": "(MMC038-02607)",
                "Amount": Decimal("1797.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("1797.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key",
                "is_ibp": True,
                "ibp_resolved_customer": "MMC038-02607 / REYNALDO MOLANO POQUIZ",
                "ibp_accounts_entry": "5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ     (1,797.00)",
            }
        ]
    )
    row = [""] * len(HEADERS)
    row[5] = "IBP TO OTHER BRANCH"
    row[10] = "-"
    rows = SHEET_ROWS + [row, [""] * len(HEADERS)]
    assert find_section_row(rows, "IBP TO OTHER BRANCH", 3)["row_number"] == 5
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "PASSED"
    assert accounts_preview.iloc[0]["Target Row"] == 6
    assert accounts_preview.iloc[0]["Section Text Col"] == 6
    assert accounts_preview.iloc[0]["Section Amount Col"] == 11


def test_accounts_ibp_section_entry_does_not_duplicate():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5083 - (MMC038-02607)",
                "OR Number": "5083",
                "Particulars": "(MMC038-02607)",
                "Amount": Decimal("1797.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("1797.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key",
                "is_ibp": True,
                "ibp_resolved_customer": "MMC038-02607 / REYNALDO MOLANO POQUIZ",
            }
        ]
    )
    rows = SHEET_ROWS + [
        ["IBP TO OTHER BRANCH", "", "", "", "", "-"],
        ["5083 - MMC038-02607 / REYNALDO MOLANO POQUIZ", "", "", "", "", "(1,797.00)"],
        ["", "", "", "", "", ""],
    ]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "DUPLICATE"
    assert prepare_sheet_updates(accounts_preview, rows, HEADERS) == []


def test_ibp_source_branch_double_encoding_uses_operator_particular():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5083 - (MMC080-00166)",
                "OR Number": "5083",
                "Particulars": "(MMC080-00166)",
                "Amount": Decimal("1797.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("353023.00"),
                "Actual Collection": Decimal("1797.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key",
                "is_ibp": True,
                "ibp_account_no": "MMC080-00166",
                "ibp_source_branch_id": "MMC080",
                "ibp_resolved_customer": "MMC080-00166 / ARGIES FEDERICO TINDAAN",
            }
        ]
    )
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC080-00166 / ARGIES FEDERICO TINDAAN", "", "", "", "", "", "", "", "", "", "", "", "88577.00", ""],
        ["", "", "", "", "", "", "", "", "", "", "", "", "", ""],
        ["IBP TO OTHER BRANCH", "", "", "", "", "-"],
        ["", "", "", "", "", ""],
        ["IBP FROM OTHER BRANCH", "", "", "", "", "-"],
        ["", "", "", "", "", ""],
    ]

    updates = prepare_ibp_source_branch_updates(parsed, rows, HEADERS, 3, {"ibp-key": "25/36 MI"}, "MMC075 - SAN CARLOS 12.25")
    values_by_cell = {(update["row"], update["col"]): update["value"] for update in updates}

    assert values_by_cell[(4, 2)] == "1-Dec-25"
    assert next(update for update in updates if update["row"] == 4 and update["col"] == 2)["value_input_option"] == "RAW"
    assert values_by_cell[(4, 3)] == "5083 IBP SAN CARLOS - (25/36 MI)"
    assert values_by_cell[(4, 9)] == "=1797"
    assert values_by_cell[(4, 14)] == "86780.00"
    assert values_by_cell[(9, 1)] == "5083 - MMC080-00166 / ARGIES FEDERICO TINDAAN"
    assert values_by_cell[(9, 6)] == "1,797.00"


def test_ibp_source_branch_numeric_particular_defaults_to_mi():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5100 - (MMC080-00166)",
                "OR Number": "5100",
                "Particulars": "(MMC080-00166)",
                "Amount": Decimal("1797.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("353023.00"),
                "Actual Collection": Decimal("1797.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key",
                "is_ibp": True,
                "ibp_account_no": "MMC080-00166",
                "ibp_source_branch_id": "MMC080",
                "ibp_resolved_customer": "MMC080-00166 / ARGIES FEDERICO TINDAAN",
            }
        ]
    )
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC080-00166 / ARGIES FEDERICO TINDAAN", "", "", "", "", "", "", "", "", "", "", "", "88577.00", ""],
        ["", "", "", "", "", "", "", "", "", "", "", "", "", ""],
        ["IBP TO OTHER BRANCH", "", "", "", "", "-"],
        ["", "", "", "", "", ""],
        ["IBP FROM OTHER BRANCH", "", "", "", "", "-"],
        ["", "", "", "", "", ""],
    ]

    updates = prepare_ibp_source_branch_updates(parsed, rows, HEADERS, 3, {"ibp-key": "26"}, "MMC075 - SAN CARLOS 12.25")
    values_by_cell = {(update["row"], update["col"]): update["value"] for update in updates}

    assert values_by_cell[(4, 3)] == "5100 IBP SAN CARLOS - (26/36 MI)"
    assert values_by_cell[(4, 9)] == "=1797"


def test_ibp_source_branch_same_account_same_date_writes_date_once():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5083 - (MMC080-00166)",
                "OR Number": "5083",
                "Particulars": "(MMC080-00166)",
                "Amount": Decimal("1000.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("353023.00"),
                "Actual Collection": Decimal("1000.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key-1",
                "is_ibp": True,
                "ibp_account_no": "MMC080-00166",
                "ibp_source_branch_id": "MMC080",
                "ibp_resolved_customer": "MMC080-00166 / ARGIES FEDERICO TINDAAN",
            },
            {
                "Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "IBP PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5084 - (MMC080-00166)",
                "OR Number": "5084",
                "Particulars": "(MMC080-00166)",
                "Amount": Decimal("797.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("353023.00"),
                "Actual Collection": Decimal("797.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "ibp-key-2",
                "is_ibp": True,
                "ibp_account_no": "MMC080-00166",
                "ibp_source_branch_id": "MMC080",
                "ibp_resolved_customer": "MMC080-00166 / ARGIES FEDERICO TINDAAN",
            },
        ]
    )
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC080-00166 / ARGIES FEDERICO TINDAAN", "", "", "", "", "", "", "", "", "", "", "", "88577.00", ""],
        ["", "", "", "", "", "", "", "", "", "", "", "", "", ""],
        ["IBP FROM OTHER BRANCH", "", "", "", "", "-"],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
    ]

    updates = prepare_ibp_source_branch_updates(
        parsed,
        rows,
        HEADERS,
        3,
        {"ibp-key-1": "25/36 MI", "ibp-key-2": "25/36 MI"},
        "MMC075 - SAN CARLOS 12.25",
    )
    values_by_cell = {(update["row"], update["col"]): update["value"] for update in updates}

    assert values_by_cell[(4, 2)] == "1-Dec-25"
    assert values_by_cell[(4, 3)] == "5083 IBP SAN CARLOS - (25/36 MI)\n5084 IBP SAN CARLOS - (25/36 MI)"
    assert values_by_cell[(4, 9)] == "=1000+797"


def test_accounts_other_payment_updates_others_section_only():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                "Account Number": "OTHER PAYMENTS",
                "Account Name Only": "MMC075-SAN CARLOS",
                "Date": "2026-05-05",
                "Reference": "5477 - (PARTS)",
                "OR Number": "5477",
                "Particulars": "(PARTS)",
                "Amount": Decimal("415.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("415.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "other-key",
                "is_ibp": False,
                "is_other_payment": True,
                "other_payment_accounts_entry": "5477 - OTHER PAYMENT /MMC075-SAN CARLOS        (415.00)",
            }
        ]
    )
    rows = SHEET_ROWS + [["OTHERS", "", "", "", "", "-"], ["", "", "", "", "", ""]]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []
    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)
    assert updates == [
        {"row": 6, "col": 1, "value": "5477 - OTHER PAYMENT /MMC075-SAN CARLOS"},
        {"row": 6, "col": 6, "value": "(415.00)"},
    ]


def test_accounts_layout_preview_keeps_section_update_inside_section_block():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                "Account Number": "OTHER PAYMENTS",
                "Account Name Only": "MMC075-SAN CARLOS",
                "Date": "2026-05-05",
                "Reference": "5477 - (PARTS)",
                "OR Number": "5477",
                "Particulars": "(PARTS)",
                "Amount": Decimal("415.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("415.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "other-key",
                "is_ibp": False,
                "is_other_payment": True,
            }
        ]
    )
    rows = SHEET_ROWS + [["OTHERS", "", "", "", "", "-"], ["", "", "", "", "", ""]]
    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    assert errors == []
    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)
    state = AppState()
    state.sheet.accounts_rows = rows
    state.sheet.accounts_headers = HEADERS
    state.posting.accounts_preview_df = accounts_preview

    layout = accounts_layout_preview(state, updates)

    assert layout["rows"][1][0] == "OTHERS"
    assert layout["rows"][2][0] == "5477 - OTHER PAYMENT /MMC075-SAN CARLOS"
    assert layout["rows"][2][4] == "(415.00)"


def test_accounts_other_payment_accepts_other_payments_section_label():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "OTHER PAYMENTS / MMC050 - SANCARLOS",
                "Account Number": "OTHER PAYMENTS",
                "Account Name Only": "MMC050 - SANCARLOS",
                "Date": "2026-05-05",
                "Reference": "5477 - (PARTS)",
                "OR Number": "5477",
                "Particulars": "(PARTS)",
                "Amount": Decimal("90.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("90.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "other-key-90",
                "is_ibp": False,
                "is_other_payment": True,
                "other_payment_accounts_entry": "5477 - OTHER PAYMENT /MMC050 - SANCARLOS        (90.00)",
            }
        ]
    )
    rows = SHEET_ROWS + [["OTHER PAYMENTS", "", "", "", "", "-"], ["", "", "", "", "", ""]]

    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)

    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "PASSED"
    assert updates == [
        {"row": 6, "col": 1, "value": "5477 - OTHER PAYMENT /MMC050 - SANCARLOS"},
        {"row": 6, "col": 6, "value": "(90.00)"},
    ]


def test_accounts_other_payment_uses_amount_column_when_section_header_has_total():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "OTHER PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2026-05-05",
                "Reference": "5085 - (PARTS)",
                "OR Number": "5085",
                "Particulars": "(PARTS)",
                "Amount": Decimal("90.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("90.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "other-key-header-total",
                "is_ibp": False,
                "is_other_payment": True,
            }
        ]
    )
    rows = SHEET_ROWS + [["OTHERS", "", "", "", "", "(90.00)"], ["", "", "", "", "", "-"]]

    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)

    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "PASSED"
    assert updates == [
        {"row": 6, "col": 1, "value": "5085 - OTHER PAYMENT /MMC075 - SAN CARLOS"},
        {"row": 6, "col": 6, "value": "(90.00)"},
    ]


def test_accounts_other_payment_can_post_after_final_section_header():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "OTHER PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2026-05-05",
                "Reference": "5085 - (PARTS)",
                "OR Number": "5085",
                "Particulars": "(PARTS)",
                "Amount": Decimal("90.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("90.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "other-key-final-section",
                "is_ibp": False,
                "is_other_payment": True,
            }
        ]
    )
    rows = SHEET_ROWS + [["OTHERS", "", "", "", "", "-"]]

    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    updates = prepare_sheet_updates(accounts_preview, rows, HEADERS)

    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "PASSED"
    assert accounts_preview.iloc[0]["Target Row"] == 6
    assert updates == [
        {"row": 6, "col": 1, "value": "5085 - OTHER PAYMENT /MMC075 - SAN CARLOS"},
        {"row": 6, "col": 6, "value": "(90.00)"},
    ]


def test_daily_collection_updates_match_date():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Date="2025-12-29")]), set())
    sheet_rows = SHEET_ROWS + [["29-Dec-25", "10.00"]]
    accounts_preview, errors = prepare_accounts_preview(parsed, sheet_rows, HEADERS, 3)
    assert errors == []
    daily_updates, daily_errors = prepare_daily_collection_updates(accounts_preview, sheet_rows)
    assert daily_errors == []
    assert daily_updates == [{"row": 5, "col": 2, "value": "=10+3000"}]


def test_accounts_preview_clears_stale_duplicate_when_sheet_row_is_blank():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row()]), {"unused"})
    parsed.loc[0, "Status"] = "DUPLICATE"
    parsed.loc[0, "Issue"] = "Duplicate transaction"
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "", "", "", "", "", "", "", "", "", "", "", "850.00", ""],
    ]

    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)

    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "PASSED"
    synced = sync_parsed_status_from_accounts_preview(parsed, accounts_preview)
    assert synced.iloc[0]["Status"] == "PASSED"


def test_accounts_preview_keeps_duplicate_when_reference_is_already_on_sheet():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row()]), {"unused"})
    parsed.loc[0, "Status"] = "DUPLICATE"
    parsed.loc[0, "Issue"] = "Duplicate transaction"
    rows = [
        ["title"],
        ["notes"],
        HEADERS,
        ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA", "2-May-26", "19045 - (21/24 MI P)", "2.00", "", "", "", "", "1999.00", "1001.00", "", "", "850.00", ""],
    ]

    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)

    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "DUPLICATE"


def test_accounts_section_duplicate_still_posts_other_tabs_and_daily_total():
    parsed = pd.DataFrame(
        [
            {
                "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                "Account Number": "OTHER PAYMENTS",
                "Account Name Only": "MMC075 - SAN CARLOS",
                "Date": "2025-12-01",
                "Reference": "5151 - (PARTS)",
                "OR Number": "5151",
                "Particulars": "(PARTS)",
                "Amount": Decimal("90.00"),
                "Interest": Decimal("0.00"),
                "Rebate": Decimal("0.00"),
                "Balance": Decimal("0.00"),
                "Actual Collection": Decimal("90.00"),
                "Status": "PASSED",
                "Issue": "",
                "Transaction Key": "other-key-5151",
                "is_ibp": False,
                "is_other_payment": True,
            }
        ]
    )
    rows = SHEET_ROWS + [
        ["01-Dec-25", "45599.00"],
        ["OTHER PAYMENTS", "", "", "", "", "-"],
        ["5151 - OTHER PAYMENT /MMC075 - SAN CARLOS", "", "", "", "", "(90.00)"],
        ["", "", "", "", "", ""],
    ]

    accounts_preview, errors = prepare_accounts_preview(parsed, rows, HEADERS, 3)
    synced = sync_parsed_status_from_accounts_preview(parsed, accounts_preview)
    daily_updates, daily_errors = prepare_daily_collection_updates(accounts_preview, rows)

    assert errors == []
    assert accounts_preview.iloc[0]["Status"] == "DUPLICATE"
    assert synced.iloc[0]["Status"] == "PASSED"
    assert passed_transaction_keys(accounts_preview) == {"other-key-5151"}
    assert daily_errors == []
    assert daily_updates == [{"row": 5, "col": 2, "value": "=45599+90"}]


def test_daily_cash_vs_mi_classification_preview():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Reference="19044 - (CASH)", Amount="22000", Interest="0"),
                simsoft_row(Reference="19045 - (21/24 MI P)", Amount="1999", Interest="1001"),
            ]
        ),
        set(),
    )
    preview = prepare_daily_preview(parsed, date(2026, 5, 1))
    assert preview.iloc[0]["CASH"] == Decimal("22000.00")
    assert preview.iloc[0]["MI"] == ""
    assert preview.iloc[1]["MI"] == Decimal("1999.00")
    assert preview.iloc[1]["TOTAL"] == Decimal("3000.00")


def test_daily_dp_mi_particular_posts_to_mi_column():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Reference="19045 - (DP/MI)", Amount="1999", Interest="1001")]), set())
    preview = prepare_daily_preview(parsed, date(2026, 5, 1))
    assert preview.iloc[0]["DP"] == ""
    assert preview.iloc[0]["MI"] == Decimal("1999.00")
    assert preview.iloc[0]["TOTAL"] == Decimal("3000.00")


def test_daily_ibp_row_output():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(
            Account_Name="IBP PAYMENTS / MMC075 - SAN CARLOS",
            Reference="5083 - (MMC038-02607)",
            Amount="1797",
            Interest="0",
        )]),
        set(),
    )
    parsed["is_ibp"] = True
    parsed["Account Number"] = "IBP PAYMENTS"
    parsed["Account Name Only"] = "MMC075 - SAN CARLOS"
    parsed["Particulars"] = "(MMC038-02607)"
    parsed["Actual Collection"] = Decimal("1797.00")
    preview = prepare_daily_preview(parsed, date(2025, 12, 1))
    assert preview.iloc[0]["ACCOUNT #"] == "IBP PAYMENTS"
    assert preview.iloc[0]["ACCOUNT NAME"] == "MMC075 - SAN CARLOS"
    assert preview.iloc[0]["PARTICULARS"] == "(MMC038-02607)"
    assert preview.iloc[0]["IBP"] == Decimal("1797.00")
    assert preview.iloc[0]["TOTAL"] == Decimal("1797.00")


def test_daily_other_payment_row_output():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "415",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    preview = prepare_daily_preview(parsed, date(2026, 5, 1))
    assert preview.iloc[0]["OR"] == "5477"
    assert preview.iloc[0]["ACCOUNT #"] == "OTHER PAYMENTS"
    assert preview.iloc[0]["ACCOUNT NAME"] == "MMC075-SAN CARLOS"
    assert preview.iloc[0]["PARTICULARS"] == "(PARTS)"
    assert preview.iloc[0]["CASH"] == ""
    assert preview.iloc[0]["DP"] == ""
    assert preview.iloc[0]["MI"] == ""
    assert preview.iloc[0]["OTHERS"] == Decimal("415.00")
    assert preview.iloc[0]["TOTAL"] == Decimal("415.00")


def test_daily_other_payment_singular_uses_reference_particulars_parts():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENT / MMC075 - SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    preview = prepare_daily_preview(annotate_other_payment_rows(parsed), "1-31")

    assert preview.iloc[0]["ACCOUNT #"] == "OTHER PAYMENT"
    assert preview.iloc[0]["ACCOUNT NAME"] == "MMC075 - SAN CARLOS"
    assert preview.iloc[0]["PARTICULARS"] == "(PARTS)"
    assert preview.iloc[0]["OTHERS"] == Decimal("90.00")
    assert preview.iloc[0]["TOTAL"] == Decimal("90.00")


def test_daily_sheet_updates_write_other_payment_to_others_column():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "415",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    preview = prepare_daily_preview(annotate_other_payment_rows(parsed), "1-31")
    rows = [
        ["#", "DATE", "OR", "ACCOUNT #", "ACCOUNT NAME", "PARTICULARS", "", "CASH", "DP", "", "MI", "REBATE", "PEN", "CM", "", "IBP", "", "OTHERS", "", "TOTAL"],
        ["1", "", "", "", "", ""],
        ["", "REMARKS"],
    ]
    updates, errors = prepare_daily_sheet_updates(preview, rows)
    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[3] == "5477"
    assert values_by_col[4] == "OTHER PAYMENTS"
    assert values_by_col[5] == "MMC075-SAN CARLOS"
    assert values_by_col[18] == "415.00"
    assert values_by_col[20] == "415.00"


def test_daily_sheet_updates_find_shifted_other_payment_column():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "415",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    preview = prepare_daily_preview(annotate_other_payment_rows(parsed), "1-31")
    rows = [
        ["#", "DATE", "OR", "ACCOUNT #", "ACCOUNT NAME", "PARTICULARS", "", "CASH", "DP", "", "MI", "REBATE", "PEN", "CM", "", "IBP", "", "", "OTHERS", "TOTAL"],
        ["1", "", "", "", "", ""],
        ["", "REMARKS"],
    ]
    updates, errors = prepare_daily_sheet_updates(preview, rows)
    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[19] == "415.00"
    assert values_by_col[20] == "415.00"


def test_daily_sheet_updates_use_blank_rows():
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Date="2025-12-29")]), set())
    preview = prepare_daily_preview(parsed, "1-31")
    rows = [
        ["#", "DATE", "OR", "ACCOUNT #", "ACCOUNT NAME", "PARTICULARS", "", "CASH", "DP", "", "MI", "REBATE", "PEN", "CM", "", "IBP", "", "OTHERS", "", "TOTAL"],
        ["1", "28-Dec-25", "old", "acct", "name", "part"],
        ["2", "", "", "", "", ""],
        ["", "REMARKS"],
    ]
    assert find_blank_daily_rows(rows) == [3]
    updates, errors = prepare_daily_sheet_updates(preview, rows)
    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[2] == "29-Dec-25"
    assert values_by_col[3] == "19045"
    assert values_by_col[4] == "MMC042-01167R"
    assert values_by_col[11] == "1999.00"
    assert values_by_col[13] == "1001.00"
    assert values_by_col[18] == ""
    assert values_by_col[20] == "3000.00"


def test_receipt_series_lookup_logic():
    headers = ["Series", "Type", "Date", "Amount"]
    rows = [headers, ["19064", "", "", ""], ["19065", "BAYAMBANG", "2026-05-02", "2166.00"]]
    index, _ = build_series_index(rows, headers, 1)
    assert index["19064"]["row_number"] == 2

    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(Reference="19064 - (28/36 MI)", Amount="1968", Interest="198")]), set())
    preview, errors = prepare_receipt_preview(parsed, "BAYAMBANG", rows, headers, 1)
    assert errors == []
    assert preview.iloc[0]["Target Row"] == 2
    assert preview.iloc[0]["Amount"] == Decimal("2166.00")

    updates = prepare_receipt_updates(preview, headers)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[2] == "CR"
    assert values_by_col[3] == "2-May-26"
    assert values_by_col[4] == "2166.00"


def test_receipt_other_payment_uses_normal_receipt_logic():
    headers = ["Series", "Type", "Date", "Amount"]
    rows = [headers, ["5477", "", "", ""]]
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "415",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    preview, errors = prepare_receipt_preview(annotate_other_payment_rows(parsed), "SAN CARLOS", rows, headers, 1)
    assert errors == []
    updates = prepare_receipt_updates(preview, headers)
    values_by_col = {update["col"]: update["value"] for update in updates}
    assert values_by_col[1] == "5477"
    assert values_by_col[2] == "CR"
    assert values_by_col[3] == "5-May-26"
    assert values_by_col[4] == "415.00"


def test_receipt_marks_skipped_or_as_canceled():
    headers = ["Type", "Series", "Date", "Amount"]
    rows = [
        headers,
        ["", "19064", "", ""],
        ["", "19065", "", ""],
        ["", "19066", "", ""],
    ]
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2026-05-02", Reference="19064 - (28/36 MI)", Amount="1968", Interest="198"),
                simsoft_row(Date="2026-05-02", Reference="19066 - (30/36 MI)", Amount="1000", Interest="100"),
            ]
        ),
        set(),
    )
    preview, errors = prepare_receipt_preview(parsed, "BAYAMBANG", rows, headers, 1)
    assert errors == []
    canceled = preview[preview["Series"] == "19065"].iloc[0]
    assert canceled["Status"] == "PASSED"
    assert canceled["Amount"] == "CANCELLED"
    updates = prepare_receipt_updates(preview, headers)
    canceled_updates = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert canceled_updates[1] == "CR"
    assert canceled_updates[3] == "2-May-26"
    assert canceled_updates[4] == "CANCELLED"


def test_receipt_missing_series_uses_blank_placeholder_row():
    headers = ["Type", "Series", "Date", "Amount"]
    rows = [
        headers,
        ["", "5150", "", ""],
        ["", "", "", ""],
        ["", "", "", ""],
    ]
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2026-05-02", Reference="5152 - (10/36 MI)", Amount="1000", Interest="50"),
            ]
        ),
        set(),
    )
    preview, errors = prepare_receipt_preview(parsed, "BAYAMBANG", rows, headers, 1)
    assert errors == []
    missing = preview[preview["Series"] == "5152"].iloc[0]
    assert missing["Status"] == "PASSED"
    assert missing["Amount"] == "CANCELLED"
    assert missing["Issue"] == "RECIEPT Series missing; inserted as canceled"
    assert missing["Series Col"] == 2
    updates = prepare_receipt_updates(preview, headers)
    assert any(update["value"] == "CANCELLED" for update in updates)
    assert any(update["col"] == 2 and update["value"] == "5152" for update in updates)


def test_skipped_receipt_uses_blank_placeholder_for_missing_5162():
    headers = ["Type", "Series", "Date", "Amount"]
    rows = [
        headers,
        ["", "5161", "2026-05-01", "1000"],
        ["", "5162", "", ""],
        ["", "5163", "", ""],
    ]
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2026-05-02", Reference="5163 - (10/36 MI)", Amount="1000", Interest="50"),
            ]
        ),
        set(),
    )
    preview, errors = prepare_receipt_preview(parsed, "BAYAMBANG", rows, headers, 1)
    assert errors == []
    missing = preview[preview["Series"] == "5162"].iloc[0]
    assert missing["Status"] == "PASSED"
    assert missing["Amount"] == "CANCELLED"
    assert missing["Issue"] == "Skipped OR marked canceled"


def test_receipt_skipped_series_stops_at_block_boundary():
    assert skipped_receipt_series(19064, 19101) == list(range(19065, 19101))
    assert skipped_receipt_series(19064, 19152) == list(range(19065, 19101))
    assert skipped_receipt_series(19050, 19051) == []


def test_receipt_block_helpers_use_exact_50_series_ranges():
    assert receipt_block_start(5151) == 5151
    assert receipt_block_end(5151) == 5200
    assert skipped_receipt_series(5151, 5178) == list(range(5152, 5178))
    assert skipped_receipt_series(5150, 5151) == []


def test_receipt_find_receipt_blocks_ignores_duplicate_header_rows():
    rows = [
        ["TYPE", "SERIES", "DATE", "AMOUNT"],
        ["CR", "5151", "02-May-26", "1000"],
        ["TYPE", "SERIES", "DATE", "AMOUNT"],
        ["CR", "5152", "02-May-26", "1000"],
    ]
    blocks = find_receipt_blocks(rows)
    assert len(blocks) == 1
    assert blocks[0]["type_col"] == 0
    assert blocks[0]["header_row_index"] == 0


def test_receipt_find_receipt_blocks_scans_later_same_column_blocks():
    rows = [["TYPE", "SERIES", "DATE", "AMOUNT"], ["CR", "5151", "02-May-26", "1000"]]
    rows.extend([["", "", "", ""] for _ in range(50)])
    rows.extend([["TYPE", "SERIES", "DATE", "AMOUNT"], ["CR", "5201", "02-May-26", "1000"]])

    blocks = find_receipt_blocks(rows)

    assert len(blocks) == 2
    assert blocks[0]["header_row_index"] == 0
    assert blocks[1]["header_row_index"] == 52


def test_receipt_find_receipt_blocks_includes_empty_blocks():
    rows = [["TYPE", "SERIES", "DATE", "AMOUNT"]]

    blocks = find_receipt_blocks(rows)

    assert len(blocks) == 1
    assert blocks[0]["header_row_index"] == 0


def test_receipt_indexes_series_after_repeated_header_row():
    headers = ["Type", "Series", "Date", "Amount"]
    rows = [
        headers,
        ["CR", "5130", "02-May-26", "1000"],
        ["TYPE", "SERIES", "DATE", "AMOUNT"],
        ["CR", "5131", "02-May-26", "1000"],
    ]
    index, _ = build_series_index(rows, headers, 1)
    assert "5130" in index
    assert "5131" in index
    assert index["5131"]["row_number"] == 4


def test_receipt_does_not_cancel_across_block_boundaries():
    headers = ["Type", "Series", "Date", "Amount"]
    rows = [headers] + [["", str(i), "", ""] for i in range(19030, 19101)]
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2026-05-02", Reference="19030 - (10/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19031 - (11/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19032 - (12/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19033 - (13/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19034 - (14/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19035 - (15/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19071 - (15/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19072 - (16/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19073 - (17/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19074 - (18/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19076 - (19/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19077 - (20/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19078 - (21/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19079 - (22/36 MI)", Amount="1000", Interest="50"),
                simsoft_row(Date="2026-05-02", Reference="19080 - (23/36 MI)", Amount="1000", Interest="50"),
            ]
        ),
        set(),
    )
    preview, errors = prepare_receipt_preview(parsed, "BAYAMBANG", rows, headers, 1)
    assert errors == []
    assert preview[preview["Series"] == "19036"].empty
    assert preview[preview["Series"] == "19050"].empty
    assert preview[preview["Series"] == "19075"].iloc[0]["Amount"] == "CANCELLED"


def test_scr_vs_br_receipt_block_continuation_and_single_or_rule():
    or_amounts = {
        18947: Decimal("1000.00"),
        18948: Decimal("1000.00"),
        19043: Decimal("3000.00"),
        19044: Decimal("22000.00"),
        19045: Decimal("2380.00"),
        19064: Decimal("2166.00"),
    }
    blocks, unused = build_receipt_blocks(
        or_amounts,
        {"BRANCH RECEIPT 1": 19042, "BRANCH RECEIPT 2": 19063, "COLLECTOR RECEIPT 2": 18946},
    )
    assert unused == []
    assert blocks[0]["FROM"] == 19043
    assert blocks[0]["TO"] == 19045
    assert blocks[0]["AMOUNT"] == Decimal("27380.00")
    assert blocks[1]["FROM"] == 19064
    assert blocks[1]["TO"] == ""
    assert blocks[1]["AMOUNT"] == Decimal("2166.00")
    assert blocks[2]["FROM"] == 18947
    assert blocks[2]["TO"] == 18948


def test_scr_vs_br_or_rule_helpers_parse_continue_and_append():
    assert parse_or_range(" OR 1001 - OR 1050 ")["valid"]
    assert get_or_start("1001-1050") == 1001
    assert get_or_end("1001-1050") == 1050
    assert is_continueable_or("1001-1050", "1051-1100")
    assert not is_continueable_or("1001-1050", "2001-2050")
    assert not is_continueable_or("bad", "1051-1100")
    assert append_or_normally("1001-1050", "1051-1100") == "1001-1100"
    assert append_or_with_breakline("1001-1050", "2001-2050") == "1001-1050\n2001-2050"


def test_scr_vs_br_updates_match_date_and_continue_nearest_block():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-29", Reference="5163 - (14/36 MI)", Amount="2097", Interest="105"),
                simsoft_row(Date="2025-12-29", Reference="5164 - (30/36 MI)", Amount="1860", Interest="93"),
                simsoft_row(Date="2025-12-29", Reference="5165 - (35-36/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-29", Reference="5166 - (17-18/24 MI P)", Amount="2004", Interest="96"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Dec-25", "14327.00", "", "5126", "5129", "8827.00", "5160", "5161", "5500.00"],
        ["29-Dec-25", "", "", "", "", "", "", "", ""],
    ]
    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)
    assert errors == []
    assert preview.iloc[0]["Block"] == "COLLECTOR RECEIPT 1"
    assert preview.iloc[0]["FROM"] == 5163
    assert preview.iloc[0]["TO"] == 5166
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert 2 not in values_by_col
    assert values_by_col[7] == "5163"
    assert values_by_col[8] == "5166"
    assert values_by_col[9] == "=2202+1953+2000+2100"


def test_scr_layout_preview_includes_previous_date_or_context():
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["23-Nov-25", "1000.00", "", "4800", "4801", "1000.00", "", "", ""],
        ["24-Nov-25", "1000.00", "", "4900", "4901", "1000.00", "", "", ""],
        ["25-Nov-25", "", "", "", "", "", "", "", ""],
        ["26-Nov-25", "1000.00", "", "4998", "4999", "1000.00", "", "", ""],
        ["27-Nov-25", "1000.00", "", "5000", "5004", "1000.00", "", "", ""],
        ["28-Nov-25", "", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "", "", "", "", "", ""],
        ["30-Nov-25", "", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", ""],
    ]
    state = AppState()
    state.sheet.scr_rows = rows
    updates = [
        {"row": 10, "col": 2, "value": "2000.00"},
        {"row": 10, "col": 4, "value": "5005"},
        {"row": 10, "col": 5, "value": "5006"},
    ]

    layout = scr_layout_preview(state, updates)

    assert layout["rows"][0][0] == "SCR DATE"
    assert len(layout["rows"]) == 5
    assert not any(row[0] in {"23-Nov-25", "25-Nov-25", "28-Nov-25", "29-Nov-25", "30-Nov-25"} for row in layout["rows"])
    assert any(row[:9] == ["24-Nov-25", "1000.00", "", "4900", "4901", "1000.00", "", "", ""] for row in layout["rows"])
    assert any(row[:9] == ["26-Nov-25", "1000.00", "", "4998", "4999", "1000.00", "", "", ""] for row in layout["rows"])
    assert any(row[:9] == ["27-Nov-25", "1000.00", "", "5000", "5004", "1000.00", "", "", ""] for row in layout["rows"])
    assert layout["rows"][1][0] == "24-Nov-25"
    assert layout["rows"][2][0] == "26-Nov-25"
    assert layout["rows"][3][0] == "27-Nov-25"
    assert layout["rows"][4][0] == "01-Dec-25"
    assert layout["rows"][4][3] == "5005"


def test_scr_vs_br_reports_skipped_source_rows_when_no_rows_are_postable():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-22", Reference="5101 - (14/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-23", Reference="5102 - (15/36 MI)", Amount="1000", Interest="0"),
            ]
        ),
        set(),
    )
    parsed["Status"] = "DUPLICATE"
    parsed["Issue"] = "Already reviewed in ACCOUNTS"
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT"],
        ["22-Dec-25", "", "", "", "", ""],
        ["23-Dec-25", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert updates == []
    assert errors == []
    assert list(preview["SCR DATE"]) == ["2025-12-22", "2025-12-23"]
    assert list(preview["Status"]) == ["SKIPPED", "SKIPPED"]
    assert all("Already reviewed in ACCOUNTS" in issue for issue in preview["Issue"])


def test_scr_vs_br_reports_missing_december_dates_when_no_updates_can_be_planned():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-22", Reference="5101 - (14/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-23", Reference="5102 - (15/36 MI)", Amount="1000", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT"],
        ["01-Jan-25", "", "", "", "", ""],
        ["02-Jan-25", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert updates == []
    assert errors == ["SCR VS BR date not found: 2025-12-22", "SCR VS BR date not found: 2025-12-23"]
    assert list(preview["SCR DATE"]) == ["2025-12-22", "2025-12-23"]
    assert list(preview["Status"]) == ["ERROR", "ERROR"]


def test_scr_vs_br_other_day_continueable_uses_normal_append_placement():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-02", Reference="1051 - (14/36 MI)", Amount="100", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="1052 - (15/36 MI)", Amount="200", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "1050", "5000.00", "", "", ""],
        ["02-Dec-25", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "NORMAL_APPEND"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "1051"
    assert values_by_col[5] == "1052"


def test_scr_vs_br_other_day_non_continueable_closed_previous_preserves_space():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(Date="2025-12-02", Reference="2001 - (14/36 MI)", Amount="100", Interest="0")]),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "1050", "5000.00", "", "", ""],
        ["02-Dec-25", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "BREAKLINE_APPEND"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "2001"


def test_scr_vs_br_other_day_noncontinueable_does_not_take_block_with_continuation():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-02", Reference="1051 - (14/36 MI)", Amount="100", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="2001 - (14/36 MI)", Amount="200", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "1050", "5000.00", "", "", ""],
        ["02-Dec-25", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert list(preview["SCRVSBR OR Placement"]) == ["NORMAL_APPEND", "NEW_SPACE"]
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "1051"
    assert values_by_col[7] == "2001"


def test_scr_vs_br_other_day_non_continueable_open_previous_uses_new_space():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(Date="2025-12-02", Reference="2001 - (14/36 MI)", Amount="100", Interest="0")]),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "", "5000.00", "", "", ""],
        ["02-Dec-25", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "NEW_SPACE"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[7] == "2001"


def test_scr_vs_br_same_day_continueable_closed_block_merges_normally():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="1051 - (14/36 MI)", Amount="100", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="1052 - (15/36 MI)", Amount="200", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "1050", "5000.00", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "NORMAL_APPEND"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "1001"
    assert values_by_col[5] == "1052"


def test_scr_vs_br_receipt_block_decides_if_continueable_or_can_merge():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(Date="2025-12-01", Reference="5083 - (14/36 MI)", Amount="100", Interest="0")]),
        set(),
    )
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5080", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5081", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5082", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5083", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "5080", "5082", "5000.00", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    assert preview.iloc[0]["Block"] == "BRANCH RECEIPT"
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "NORMAL_APPEND"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=5000+100"


def test_scr_vs_br_same_day_non_continueable_closed_block_breaklines():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(Date="2025-12-01", Reference="2001 - (14/36 MI)", Amount="100", Interest="0")]),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "1050", "5000.00", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "BREAKLINE_APPEND"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "1001\n2001"
    assert values_by_col[5] == "1050"


def test_scr_vs_br_continueable_or_then_non_continueable_uses_open_space():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5101 - (14/36 MI)", Amount="100", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5151 - (PARTS)", Amount="200", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "5080", "5100", "5000.00", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert list(preview["SCRVSBR OR Placement"]) == ["NORMAL_APPEND", "BREAKLINE_APPEND"]
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "5080\n5151"
    assert values_by_col[5] == "5101"
    assert values_by_col[6] == "=5000+100+200"
    assert 7 not in values_by_col
    assert 8 not in values_by_col


def test_scr_vs_br_noncontinueable_uses_closed_previous_day_block_after_continuation():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5101 - (PARTS)", Amount="90", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5151 - (PARTS)", Amount="90", Interest="0"),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "5080", "5100", "44599.00", "", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert list(preview["SCRVSBR OR Placement"]) == ["NORMAL_APPEND", "BREAKLINE_APPEND"]
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[4] == "5080\n5151"
    assert values_by_col[5] == "5101"
    assert values_by_col[6] == "=44599+90+90"
    assert 7 not in values_by_col
    assert 8 not in values_by_col
    assert 10 not in values_by_col
    assert 11 not in values_by_col


def test_scr_vs_br_noncontinueable_closed_previous_day_wins_over_open_space_after_continuation():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5100 - (MMC080-00166)", Amount="2000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5101 - (PARTS)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5151 - (PARTS)", Amount="90", Interest="0"),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5080", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5100", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5101", "Type Col": 9, "Series Col": 10, "Date Col": 11, "Amount Col": 12, "Status": "PASSED"},
            {"Series": "5151", "Type Col": 13, "Series Col": 14, "Date Col": 15, "Amount Col": 16, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    assert list(preview["SCRVSBR OR Placement"]) == ["NORMAL_APPEND", "NORMAL_APPEND", "BREAKLINE_APPEND"]
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5101"
    assert values_by_col[6] == "=1000+2000+1000"
    assert values_by_col[7] == "5151"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "90.00"
    assert 10 not in values_by_col


def test_scr_vs_br_duplicate_or_range_blocks_posting():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame([simsoft_row(Date="2025-12-01", Reference="1020 - (14/36 MI)", Amount="100", Interest="0")]),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1001", "1050", "5000.00"],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert "Duplicate SCR VS BR OR posting blocked: 1020" in errors
    assert preview.iloc[0]["SCRVSBR OR Placement"] == "BLOCK_POSTING_DUPLICATE_OR"
    assert updates == []


def test_scr_vs_br_latest_before_uses_nearest_previous_row_not_highest_or():
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT"],
        ["old", "", "", "7280", "7284", ""],
        ["29-Nov-25", "", "", "5075", "5079", ""],
        ["01-Dec-25", "", "", "", "", ""],
    ]
    assert _latest_or_before_row(rows, 4, 4, 5) == 5079


def test_scr_vs_br_splits_continuous_numbers_by_block_continuation():
    or_amounts = {number: Decimal("0.00") for number in range(5037, 5084)}
    or_amounts.update(
        {
            5037: Decimal("1000.00"),
            5080: Decimal("2000.00"),
            5081: Decimal("2000.00"),
            5082: Decimal("1910.00"),
            5083: Decimal("1797.00"),
        }
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", ""],
    ]
    assigned, unassigned = assign_scr_blocks(contiguous_or_ranges(or_amounts), rows, 5)
    assert unassigned == []
    branch = next(block for block in assigned if block["from_col"] == 4)
    collector = next(block for block in assigned if block["from_col"] == 7)
    assert branch["FROM"] == 5080
    assert branch["TO"] == 5083
    assert branch["AMOUNT"] == Decimal("7707.00")
    assert collector["FROM"] == 5037
    assert collector["TO"] == 5079
    assert collector["AMOUNT"] == Decimal("1000.00")


def test_scr_vs_br_updates_split_december_first_like_sheet():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (8/24 MI)", Amount="1819", Interest="91"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC038-02607)", Amount="1797", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", ""],
    ]
    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)
    assert errors == []
    records = {(row["FROM"], row["TO"]): row for _, row in preview.iterrows()}
    assert records[(5080, 5083)]["Block"] == "BRANCH RECEIPT"
    assert records[(5080, 5083)]["AMOUNT"] == Decimal("7707.00")
    assert records[(5037, "")]["Block"] == "COLLECTOR RECEIPT 1"
    assert records[(5037, "")]["AMOUNT"] == Decimal("1000.00")
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert 2 not in values_by_col
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=2000+2000+1910+1797"
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"


def test_scr_vs_br_keeps_far_same_day_or_out_of_new_empty_range():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5101 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    records = {(row["Block"], row["FROM"], row["TO"]): row for _, row in preview.iterrows()}
    assert records[("BRANCH RECEIPT", 5080, 5083)]["AMOUNT"] == Decimal("44599.00")
    assert records[("COLLECTOR RECEIPT 1", 5037, "")]["AMOUNT"] == Decimal("1000.00")
    assert records[("COLLECTOR RECEIPT 2", 5101, "")]["AMOUNT"] == Decimal("90.00")
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=2000+9879+30923+1797"
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"


def test_scr_vs_br_far_or_prefers_done_block_over_free_space():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5101 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["29-Nov-25", "", "", "5075", "5079", "", "", "", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "", "", "", "5001", "5002", "100.00", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    records = {(row["Block"], row["FROM"], row["TO"]): row for _, row in preview.iterrows()}
    assert records[("BRANCH RECEIPT", 5080, 5083)]["AMOUNT"] == Decimal("44599.00")
    assert records[("COLLECTOR RECEIPT 2", 5101, "")]["AMOUNT"] == Decimal("90.00")
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=2000+9879+30923+1797"
    assert 7 not in values_by_col
    assert 8 not in values_by_col
    assert 9 not in values_by_col
    assert values_by_col[10] == "5101"
    assert values_by_col[11] == ""
    assert values_by_col[12] == "90.00"


def test_scr_vs_br_corrects_far_or_already_written_inside_open_block():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5101 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "45689.00", "", "5080\n5101", "5083", "44689.00", "5037", "", "1000.00", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    records = {(row["Block"], row["FROM"], row["TO"]): row for _, row in preview.iterrows()}
    assert records[("BRANCH RECEIPT", 5080, 5083)]["AMOUNT"] == Decimal("44599.00")
    assert records[("COLLECTOR RECEIPT 1", 5037, "")]["AMOUNT"] == Decimal("1000.00")
    assert records[("BRANCH RECEIPT", 5101, "")]["AMOUNT"] == Decimal("90.00")
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[4] == "5080\n5101"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=2000+9879+30923+1797+90"
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"


def test_scr_vs_br_groups_ors_by_receipt_physical_block():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5101 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5037", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5080", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5081", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5082", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5083", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5101", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "45689.00", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    records = {(row["Block"], row["FROM"], row["TO"]): row for _, row in preview.iterrows()}
    assert records[("BRANCH RECEIPT", 5080, 5083)]["AMOUNT"] == Decimal("44599.00")
    assert records[("COLLECTOR RECEIPT 1", 5037, "")]["AMOUNT"] == Decimal("1000.00")
    assert records[("COLLECTOR RECEIPT 2", 5101, "")]["AMOUNT"] == Decimal("90.00")
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=2000+9879+30923+1797"
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"
    assert values_by_col[10] == "5101"
    assert values_by_col[11] == ""
    assert values_by_col[12] == "90.00"


def test_scr_vs_br_new_receipt_group_breaklines_under_done_block():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-02", Reference="5101 - (PARTS)", Amount="90", Interest="0"),
            ]
        ),
        set(),
    )
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5101", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["02-Dec-25", "", "", "5037", "5083", "45599.00", "", "", "", "", "", "", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    assert preview.iloc[0]["Block"] == "BRANCH RECEIPT"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "5037\n5101"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=45599+90"


def test_scr_vs_br_clears_stale_block_when_moving_or_under_done_block():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5151 - (PARTS)", Amount="90", Interest="0"),
            ]
        ),
        set(),
    )
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5151", "Type Col": 9, "Series Col": 10, "Date Col": 11, "Amount Col": 12, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "45689.00", "", "5080", "5100", "44599.00", "5037", "", "1000.00", "5151", "", "90.00", "", "", ""],
    ]

    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert 4 not in values_by_col
    assert values_by_col[10] == "5151"
    assert values_by_col[11] == ""
    assert values_by_col[12] == "90.00"


def test_scr_vs_br_same_day_closed_block_wins_over_free_space_even_when_current_or_overlaps():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5151 - (PARTS)", Amount="90", Interest="0"),
            ]
        ),
        set(),
    )
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5080", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5151", "Type Col": 9, "Series Col": 10, "Date Col": 11, "Amount Col": 12, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "45689.00", "", "5080", "5100", "44599.00", "5037", "", "1000.00", "5151", "", "90.00", "", "", ""],
    ]

    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[10] == "5151"
    assert values_by_col[11] == ""
    assert values_by_col[12] == "90.00"


def test_scr_vs_br_exact_5100_5151_case_breaklines_under_closed_block():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5100 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5151 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5037", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5080", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5081", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5082", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5100", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5151", "Type Col": 13, "Series Col": 14, "Date Col": 15, "Amount Col": 16, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "45689.00", "", "5080", "5100", "44599.00", "5037", "", "1000.00", "5151", "", "90.00", "", "", ""],
    ]

    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"
    assert values_by_col[10] == "5151"
    assert values_by_col[11] == ""
    assert values_by_col[12] == "90.00"
    assert 13 not in values_by_col
    assert 14 not in values_by_col
    assert 15 not in values_by_col


def test_scr_vs_br_exact_5100_5151_first_post_uses_closed_block_layout():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5100 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5151 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5037", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5080", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5081", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5082", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5100", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5151", "Type Col": 13, "Series Col": 14, "Date Col": 15, "Amount Col": 16, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]

    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[4] == "5080\n5151"
    assert values_by_col[5] == "5100"
    assert values_by_col[6] == "=2000+9879+30923+1797+90"
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"
    assert 10 not in values_by_col
    assert 13 not in values_by_col


def test_scr_vs_br_uses_sequence_after_receipt_scan_for_backward_or():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5050 - (PARTS)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC038-02607)", Amount="1797", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5100 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5151 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    receipt_preview = pd.DataFrame(
        [
            {"Series": "5050", "Type Col": 1, "Series Col": 2, "Date Col": 3, "Amount Col": 4, "Status": "PASSED"},
            {"Series": "5080", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5081", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5082", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5083", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5100", "Type Col": 5, "Series Col": 6, "Date Col": 7, "Amount Col": 8, "Status": "PASSED"},
            {"Series": "5151", "Type Col": 13, "Series Col": 14, "Date Col": 15, "Amount Col": 16, "Status": "PASSED"},
        ]
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", "", "", "", "", "", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", "", "", "", "", "", "", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5049", "", "", "", "", "", "", ""],
        ["01-Dec-25", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]

    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows, receipt_preview)

    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert values_by_col[4] == "5080\n5151"
    assert values_by_col[5] == "5100"
    assert values_by_col[7] == "5050"
    assert 10 not in values_by_col


def test_scr_vs_br_exact_5100_5151_case_works_without_receipt_metadata():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="9786", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (CASH)", Amount="30923", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5100 - (MMC080-00166)", Amount="1797", Interest="0"),
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075 - SAN CARLOS",
                        "Date": "2025-12-01",
                        "Reference": "5151 - (PARTS)",
                        "Amount": "90",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                ),
            ]
        ),
        set(),
    )
    parsed = annotate_other_payment_rows(parsed)
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "45689.00", "", "5080", "5100", "44599.00", "5037", "", "1000.00", "5151", "", "90.00", "", "", ""],
    ]

    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"
    assert values_by_col[10] == "5151"
    assert values_by_col[11] == ""
    assert values_by_col[12] == "90.00"


def test_scr_vs_br_replaces_wrong_same_day_overlap_with_correct_blocks():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-01", Reference="5037 - (13/24 MI P", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-01", Reference="5080 - (25-26/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5081 - (31-32/36 MI P)", Amount="1907", Interest="93"),
                simsoft_row(Date="2025-12-01", Reference="5082 - (8/24 MI)", Amount="1819", Interest="91"),
                simsoft_row(Date="2025-12-01", Reference="5083 - (MMC038-02607)", Amount="1797", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["27-Nov-25", "", "", "5068", "5069", "", "5032", "", ""],
        ["28-Nov-25", "", "", "5070", "5074", "", "5033", "5034", ""],
        ["29-Nov-25", "", "", "5075", "5079", "", "5035", "5036", ""],
        ["01-Dec-25", "17414.00", "", "", "", "", "5037", "5083", "8707.00"],
    ]
    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows)
    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 5}
    assert 2 not in values_by_col
    assert values_by_col[4] == "5080"
    assert values_by_col[5] == "5083"
    assert values_by_col[6] == "=2000+2000+1910+1797"
    assert values_by_col[7] == "5037"
    assert values_by_col[8] == ""
    assert values_by_col[9] == "1000.00"


def test_scr_vs_br_other_payment_single_or_has_blank_to():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(
                    **{
                        "Account Name": "OTHER PAYMENTS / MMC075-SAN CARLOS",
                        "Date": "2026-05-05",
                        "Reference": "5477 - (PARTS)",
                        "Amount": "415",
                        "Interest": "0",
                        "Rebate": "0",
                    }
                )
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT"],
        ["04-May-26", "", "", "5476", "", "100.00"],
        ["05-May-26", "", "", "", "", ""],
    ]
    preview, updates, errors = prepare_scr_vs_br_updates(annotate_other_payment_rows(parsed), rows)
    assert errors == []
    assert preview.iloc[0]["FROM"] == 5477
    assert preview.iloc[0]["TO"] == ""
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "5477"
    assert values_by_col[5] == ""
    assert values_by_col[6] == "415.00"


def test_scr_vs_br_keeps_skipped_or_in_range_with_zero_amount():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2026-05-02", Reference="19064 - (28/36 MI)", Amount="1968", Interest="198"),
                simsoft_row(Date="2026-05-02", Reference="19066 - (30/36 MI)", Amount="1000", Interest="100"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT"],
        ["01-May-26", "", "", "19060", "19063", "1000.00"],
        ["02-May-26", "", "", "", "", ""],
    ]
    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)
    assert errors == []
    assert preview.iloc[0]["FROM"] == 19064
    assert preview.iloc[0]["TO"] == 19066
    assert preview.iloc[0]["Skipped ORs"] == "19065"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert 2 not in values_by_col
    assert values_by_col[4] == "19064"
    assert values_by_col[5] == "19066"
    assert values_by_col[6] == "=2166+1100"


def test_scr_vs_br_appends_multiple_ranges_to_same_block_on_same_date():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-10-01", Reference="18101 - (14/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-10-01", Reference="18102 - (15/36 MI)", Amount="2000", Interest="0"),
                simsoft_row(Date="2025-10-01", Reference="18201 - (16/36 MI)", Amount="3000", Interest="0"),
                simsoft_row(Date="2025-10-01", Reference="18202 - (17/36 MI)", Amount="4000", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["30-Sep-25", "", "", "", "", "", "", "", "", "", "", "", "18099", "18100", "4000.00"],
        ["01-Oct-25", "11486.00", "", "", "", "", "", "", "", "", "", "", "18045", "18046", "7486.00"],
    ]
    _, updates, errors = prepare_scr_vs_br_updates(parsed, rows)
    assert errors == []
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert 2 not in values_by_col
    assert values_by_col[13] == "18045\n18101"
    assert values_by_col[14] == "18046\n18102"
    assert values_by_col[15] == "=7486+1000+2000"
    assert values_by_col[4] == "18201"
    assert values_by_col[5] == "18202"
    assert values_by_col[6] == "=3000+4000"


def test_scr_vs_br_joins_completed_block_when_no_empty_space_available():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-10-01", Reference="19001 - (14/36 MI)", Amount="1000", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Oct-25", "", "", "18001", "18002", "2000.00", "18501", "18502", "3000.00", "18601", "18602", "4000.00", "18701", "18702", "5000.00"],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["Block"] == "BRANCH RECEIPT"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "18001\n19001"
    assert values_by_col[5] == "18002"
    assert values_by_col[6] == "=2000+1000"


def test_scr_vs_br_far_gap_joins_done_block_not_unfinished_block_when_full():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-02", Reference="80 - (14/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="81 - (15/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="82 - (16/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="83 - (17/36 MI)", Amount="1000", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["01-Dec-25", "", "", "1", "10", "10000.00", "50", "65", "16000.00", "100", "110", "11000.00", "120", "130", "11000.00"],
        ["02-Dec-25", "", "", "1", "10", "10000.00", "50", "65", "16000.00", "100", "110", "11000.00", "120", "130", "11000.00"],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["Block"] == "BRANCH RECEIPT"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 3}
    assert values_by_col[4] == "1\n80"
    assert values_by_col[5] == "10\n83"
    assert values_by_col[6] == "=10000+1000+1000+1000+1000"
    assert 7 not in values_by_col
    assert 8 not in values_by_col
    assert 9 not in values_by_col


def test_scr_vs_br_far_gap_joins_done_block_even_with_empty_space():
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(Date="2025-12-02", Reference="80 - (14/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="81 - (15/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="82 - (16/36 MI)", Amount="1000", Interest="0"),
                simsoft_row(Date="2025-12-02", Reference="83 - (17/36 MI)", Amount="1000", Interest="0"),
            ]
        ),
        set(),
    )
    rows = [
        ["SCR DATE", "AMOUNT", "", "FROM", "TO", "AMOUNT", "FROM", "TO", "AMOUNT"],
        ["02-Dec-25", "", "", "1", "10", "10000.00", "", "", ""],
    ]

    preview, updates, errors = prepare_scr_vs_br_updates(parsed, rows)

    assert errors == []
    assert preview.iloc[0]["Block"] == "BRANCH RECEIPT"
    values_by_col = {update["col"]: update["value"] for update in updates if update["row"] == 2}
    assert values_by_col[4] == "1\n80"
    assert values_by_col[5] == "10\n83"
    assert values_by_col[6] == "=10000+1000+1000+1000+1000"
    assert 7 not in values_by_col
    assert 8 not in values_by_col
    assert 9 not in values_by_col


def test_confirmation_blocker_logic():
    assert can_confirm_post(True, True, False, "CONFIRM", True)
    assert not can_confirm_post(True, True, False, "confirm", True)
    assert not can_confirm_post(True, True, False, "CONFIRM", False)
    assert not can_confirm_post(True, True, True, "CONFIRM", True)


def test_reconciliation_variance_calculation():
    assert reconciliation_variance("3000", "2999.50") == Decimal("0.50")


def test_service_account_json_validation():
    validate_service_account_info(
        {
            "type": "service_account",
            "project_id": "project",
            "private_key": "key",
            "client_email": "service@example.iam.gserviceaccount.com",
            "client_id": "123456789",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    with pytest.raises(ValueError):
        validate_service_account_info({"type": "authorized_user"})
    with pytest.raises(ValueError):
        validate_service_account_info(
            {
                "type": "service_account",
                "project_id": "project",
                "private_key": "key",
                "client_email": "service@example.iam.gserviceaccount.com",
                "client_id": "https://docs.google.com/spreadsheets/d/example/edit",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )


def test_oauth_client_json_validation_rejects_placeholder_values():
    with pytest.raises(ValueError, match="placeholder"):
        validate_oauth_client_info(
            {
                "installed": {
                    "client_id": "REPLACE_WITH_DESKTOP_OAUTH_CLIENT_ID.apps.googleusercontent.com",
                    "project_id": "REPLACE_WITH_GOOGLE_CLOUD_PROJECT_ID",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": "REPLACE_WITH_DESKTOP_OAUTH_CLIENT_SECRET",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )


def test_oauth_client_json_validation_accepts_desktop_client_shape():
    validate_oauth_client_info(
        {
            "installed": {
                "client_id": "1234567890-example.apps.googleusercontent.com",
                "project_id": "simsoft-project",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_secret": "real-looking-secret",
                "redirect_uris": ["http://localhost"],
            }
        }
    )


def test_oauth_token_storage_protection_roundtrip():
    raw = '{"token": "access-token", "refresh_token": "refresh-token"}'
    protected = protect_oauth_token_json(raw)
    assert unprotect_oauth_token_json(protected) == raw
    if protected != raw:
        assert "access-token" not in protected
        assert "refresh-token" not in protected


def test_oauth_token_encryption_marker_detection(tmp_path):
    token_path = tmp_path / "operator.json"
    token_path.write_text('{"token": "plain"}', encoding="utf-8")
    assert not oauth_token_file_is_encrypted(token_path)
    token_path.write_text(protect_oauth_token_json('{"token": "plain"}'), encoding="utf-8")
    assert oauth_token_file_is_encrypted(token_path) is (protect_oauth_token_json('{"token": "plain"}') != '{"token": "plain"}')


def test_corrupt_oauth_token_is_cleared(tmp_path):
    from core.google_sheets import active_oauth_user_path, load_user_oauth_credentials, oauth_token_path_for_email

    email = "operator@example.com"
    active_oauth_user_path(tmp_path).write_text(email, encoding="utf-8")
    oauth_token_path_for_email(email, tmp_path).write_text("{bad json", encoding="utf-8")

    credentials, loaded_email = load_user_oauth_credentials(tmp_path)

    assert credentials is None
    assert loaded_email == email
    assert not active_oauth_user_path(tmp_path).exists()


class FakeCredentials:
    valid = True
    expired = False
    refresh_token = "refresh-token"
    token = "access-token"

    def refresh(self, request):
        self.valid = True


def _patch_google_api_build(monkeypatch):
    import sys
    import types

    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda service, version, credentials=None: {
        "service": service,
        "version": version,
        "credentials": credentials,
    }
    package = types.ModuleType("googleapiclient")
    package.discovery = discovery
    monkeypatch.setitem(sys.modules, "googleapiclient", package)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)


def test_auth_mode_selection_creates_service_account_clients(monkeypatch):
    import core.google_sheets as google_sheets

    _patch_google_api_build(monkeypatch)
    creds = FakeCredentials()
    monkeypatch.setattr(google_sheets, "get_service_account_credentials", lambda info, scopes=None: creds)
    clients = create_google_clients(
        AUTH_MODE_SERVICE_ACCOUNT,
        service_account_info={"client_email": "service@example.iam.gserviceaccount.com"},
    )

    assert clients.auth_mode == AUTH_MODE_SERVICE_ACCOUNT
    assert clients.current_user_email == "service@example.iam.gserviceaccount.com"
    assert clients.drive_service["credentials"] is creds
    assert clients.sheets_service["credentials"] is creds


def test_user_oauth_client_creation_with_mocked_credentials(monkeypatch):
    import core.google_sheets as google_sheets

    _patch_google_api_build(monkeypatch)
    creds = FakeCredentials()
    monkeypatch.setattr(google_sheets, "get_oauth_user_email", lambda credentials: "operator@example.com")

    clients = create_google_clients(AUTH_MODE_USER_OAUTH, credentials=creds)

    assert clients.auth_mode == AUTH_MODE_USER_OAUTH
    assert clients.current_user_email == "operator@example.com"
    assert clients.drive_service["credentials"] is creds


def test_user_oauth_posting_is_blocked_without_signed_in_user():
    assert not can_confirm_post(True, True, False, "CONFIRM", True, auth_signed_in=False)


def test_fetch_worksheet_rows_uses_user_credentials_when_oauth_selected(monkeypatch):
    import core.google_sheets as google_sheets

    captured = {}

    class FakeWorksheet:
        def get_all_values(self):
            return [["ACCOUNT"], ["value"]]

    class FakeSpreadsheet:
        def worksheet(self, name):
            return FakeWorksheet()

    class FakeClient:
        def open_by_key(self, spreadsheet_id):
            captured["spreadsheet_id"] = spreadsheet_id
            return FakeSpreadsheet()

    def fake_get_gspread_client(auth_context):
        captured["auth_context"] = auth_context
        return FakeClient()

    user_auth = {
        "auth_mode": AUTH_MODE_USER_OAUTH,
        "credentials": FakeCredentials(),
        "current_user_email": "operator@example.com",
    }
    monkeypatch.setattr(google_sheets, "get_gspread_client", fake_get_gspread_client)

    worksheet, rows = fetch_worksheet_rows("https://docs.google.com/spreadsheets/d/sheet123/edit", "ACCOUNTS", user_auth)

    assert rows == [["ACCOUNT"], ["value"]]
    assert captured["spreadsheet_id"] == "sheet123"
    assert captured["auth_context"] is user_auth
    assert google_actor_email(user_auth) == "operator@example.com"


def test_branch_folder_scan_uses_selected_auth_mode(monkeypatch):
    import json
    from io import BytesIO
    import core.branch_folder_lookup as branch_folder_lookup

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return BytesIO(
                json.dumps(
                    {
                        "files": [
                            {
                                "id": "sheet1",
                                "name": "MMC038 - POZORRUBIO REALTIME 2026",
                                "mimeType": "application/vnd.google-apps.spreadsheet",
                            }
                        ]
                    }
                ).encode("utf-8")
            )

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=None):
        captured["authorization"] = request.headers.get("Authorization")
        captured["url"] = request.full_url
        return FakeResponse()

    user_auth = {
        "auth_mode": AUTH_MODE_USER_OAUTH,
        "credentials": FakeCredentials(),
        "current_user_email": "operator@example.com",
    }
    monkeypatch.setattr(branch_folder_lookup, "urlopen", fake_urlopen)

    index = scan_branch_folder(user_auth, "folder123")

    assert index["MMC038"]["spreadsheet_id"] == "sheet1"
    assert captured["authorization"] == "Bearer access-token"
    assert "fields=nextPageToken" in captured["url"]
    assert "get_all_values" not in captured["url"]


def test_folder_scan_resolves_google_drive_sheet_shortcuts(monkeypatch):
    import json
    from io import BytesIO
    import core.branch_folder_lookup as branch_folder_lookup

    class FakeResponse:
        def __enter__(self):
            return BytesIO(
                json.dumps(
                    {
                        "files": [
                            {
                                "id": "shortcut1",
                                "name": "MMC042 - BAYAMBANG REALTIME 2026",
                                "mimeType": "application/vnd.google-apps.shortcut",
                                "shortcutDetails": {
                                    "targetId": "sheet-target",
                                    "targetMimeType": "application/vnd.google-apps.spreadsheet",
                                },
                            }
                        ]
                    }
                ).encode("utf-8")
            )

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(branch_folder_lookup, "urlopen", lambda request, timeout=None: FakeResponse())

    user_auth = {
        "auth_mode": AUTH_MODE_USER_OAUTH,
        "credentials": FakeCredentials(),
        "current_user_email": "operator@example.com",
    }
    index = scan_branch_folder(user_auth, "folder123")

    assert index["MMC042"]["spreadsheet_id"] == "sheet-target"
    assert index["MMC042"]["shortcut_id"] == "shortcut1"
    assert index["MMC042"]["is_shortcut"]


def test_workflow_folder_scan_is_cached_until_refresh(monkeypatch, tmp_path):
    import python_backend.services.workflow_service as workflow_service

    monkeypatch.setattr(workflow_service, "FOLDER_SCAN_CACHE_PATH", tmp_path / "branch_folder_cache.json")
    calls = {"count": 0}

    def fake_scan(auth_context, folder_id):
        calls["count"] += 1
        return [{"id": f"sheet{calls['count']}", "name": "MMC038 - POZORRUBIO REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet"}]

    monkeypatch.setattr(workflow_service, "scan_branch_folder_metadata", fake_scan)
    state = AppState(auth_ready=True, auth_context={"client_email": "svc@example.com"}, current_user_email="svc@example.com")
    service = SimsoftWorkflowService()
    folder_url = "https://drive.google.com/drive/folders/folder123"

    first = service.scan_drive_folder_cached(state, folder_url)
    second = service.scan_drive_folder_cached(state, folder_url)
    refreshed = service.scan_drive_folder_cached(state, folder_url, refresh=True)

    assert calls["count"] == 2
    assert first is second
    assert refreshed["MMC038"]["spreadsheet_id"] == "sheet2"
    assert state.cache.branch_folder == "Scanned"
    assert state.cache.branch_sheet_count == 1
    assert "drive_folder_scan_duration" in state.performance_timings
    assert "branch_index_build_duration" in state.performance_timings


def test_workflow_folder_scan_uses_disk_cache_between_sessions(monkeypatch, tmp_path):
    import python_backend.services.workflow_service as workflow_service

    monkeypatch.setattr(workflow_service, "FOLDER_SCAN_CACHE_PATH", tmp_path / "branch_folder_cache.json")
    calls = {"count": 0}

    def fake_scan(auth_context, folder_id):
        calls["count"] += 1
        return [{"id": f"sheet{calls['count']}", "name": "MMC038 - POZORRUBIO REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet"}]

    monkeypatch.setattr(workflow_service, "scan_branch_folder_metadata", fake_scan)
    state = AppState(auth_ready=True, auth_context={"client_email": "svc@example.com"}, current_user_email="svc@example.com")
    folder_url = "https://drive.google.com/drive/folders/folder123"

    first_service = SimsoftWorkflowService()
    second_service = SimsoftWorkflowService()

    first = first_service.scan_drive_folder_cached(state, folder_url)
    second = second_service.scan_drive_folder_cached(state, folder_url)
    refreshed = second_service.scan_drive_folder_cached(state, folder_url, refresh=True)

    assert first["MMC038"]["spreadsheet_id"] == "sheet1"
    assert second["MMC038"]["spreadsheet_id"] == "sheet1"
    assert refreshed["MMC038"]["spreadsheet_id"] == "sheet2"
    assert calls["count"] == 2


def test_folder_scan_does_not_read_sheet_contents(monkeypatch, tmp_path):
    import python_backend.services.workflow_service as workflow_service

    monkeypatch.setattr(workflow_service, "FOLDER_SCAN_CACHE_PATH", tmp_path / "branch_folder_cache.json")
    monkeypatch.setattr(
        workflow_service,
        "scan_branch_folder_metadata",
        lambda auth_context, folder_id: [{"id": "sheet1", "name": "MMC038 - POZORRUBIO REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet"}],
    )
    monkeypatch.setattr(workflow_service, "get_gspread_client", lambda auth_context: (_ for _ in ()).throw(AssertionError("Sheet contents should not be read during folder scan")))

    state = AppState(auth_ready=True, auth_context={"client_email": "svc@example.com"}, current_user_email="svc@example.com")
    service = SimsoftWorkflowService()
    index = service.scan_drive_folder_cached(state, "https://drive.google.com/drive/folders/folder123")

    assert index["MMC038"]["spreadsheet_id"] == "sheet1"


def test_folder_scan_cache_invalidates_when_folder_link_changes(monkeypatch, tmp_path):
    import python_backend.services.workflow_service as workflow_service

    monkeypatch.setattr(workflow_service, "FOLDER_SCAN_CACHE_PATH", tmp_path / "branch_folder_cache.json")
    calls = {"count": 0}

    def fake_scan(auth_context, folder_id):
        calls["count"] += 1
        return [{"id": f"{folder_id}-sheet", "name": "MMC038 - POZORRUBIO REALTIME 2026", "mimeType": "application/vnd.google-apps.spreadsheet"}]

    monkeypatch.setattr(workflow_service, "scan_branch_folder_metadata", fake_scan)
    state = AppState(auth_ready=True, auth_context={"client_email": "svc@example.com"}, current_user_email="svc@example.com")
    service = SimsoftWorkflowService()

    first = service.scan_drive_folder_cached(state, "https://drive.google.com/drive/folders/folder123")
    second = service.scan_drive_folder_cached(state, "https://drive.google.com/drive/folders/folder456")

    assert calls["count"] == 2
    assert first["MMC038"]["spreadsheet_id"] == "folder123-sheet"
    assert second["MMC038"]["spreadsheet_id"] == "folder456-sheet"


def test_workflow_duplicate_history_loaded_once(monkeypatch):
    calls = {"count": 0}

    class FakeStore:
        shared_warning = ""

        def transaction_keys(self):
            calls["count"] += 1
            return {"existing-key"}

    service = SimsoftWorkflowService(duplicate_store=FakeStore())

    assert service.duplicate_history() == {"existing-key"}
    assert service.duplicate_history() == {"existing-key"}
    assert calls["count"] == 1


def test_ibp_branch_account_index_cache_reads_branch_once(monkeypatch):
    branch_index = {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123"}}
    call_count = {"count": 0}

    def fake_fetch_rows(sheet_url, worksheet_name, service_account_info):
        call_count["count"] += 1
        return object(), [
            ["title"],
            ["notes"],
            ["ACCOUNT"],
            ["MMC038-02607 / REYNALDO MOLANO POQUIZ"],
            ["MMC038-02608 / SECOND CUSTOMER"],
        ]

    monkeypatch.setattr("core.ibp_resolver.fetch_worksheet_rows", fake_fetch_rows)
    parsed, _ = parse_and_validate_simsoft(
        pd.DataFrame(
            [
                simsoft_row(**{"Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS", "Reference": "5083 - (MMC038-02607)", "Amount": "1797", "Interest": "0"}),
                simsoft_row(**{"Account Name": "IBP PAYMENTS / MMC075 - SAN CARLOS", "Reference": "5084 - (MMC038-02608)", "Amount": "1797", "Interest": "0"}),
            ]
        ),
        set(),
    )

    annotated = annotate_ibp_rows(parsed, branch_index, {"client_email": "test@example.com"}, {}, {})

    assert list(annotated["Status"]) == ["PASSED", "PASSED"]
    assert call_count["count"] == 1


def test_ibp_source_branch_sheet_loaded_only_when_ibp_needed(monkeypatch):
    call_count = {"count": 0}

    def fake_fetch_rows(sheet_url, worksheet_name, service_account_info):
        call_count["count"] += 1
        raise AssertionError("IBP source sheet should not load for non-IBP rows")

    monkeypatch.setattr("core.ibp_resolver.fetch_worksheet_rows", fake_fetch_rows)
    parsed, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row(**{"Account Name": "MMC042-01167R / NORMAL USER"})]), set())

    annotated = annotate_ibp_rows(parsed, {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123"}}, {"client_email": "test@example.com"}, {}, {})

    assert not annotated.iloc[0]["is_ibp"]
    assert call_count["count"] == 0


def test_post_to_google_sheet_retries_transient_errors(monkeypatch):
    calls = {"count": 0}

    class FlakyWorksheet:
        def batch_update(self, payload, value_input_option):
            calls["count"] += 1
            if calls["count"] == 1:
                raise Exception("APIError: [429]: Quota exceeded")

    monkeypatch.setattr("core.google_sheets.time.sleep", lambda seconds: None)

    post_to_google_sheet(FlakyWorksheet(), [{"row": 1, "col": 1, "value": "ok"}])

    assert calls["count"] == 2


def test_branch_posting_lock_acquire_release(tmp_path):
    store = LocalCsvDuplicateAuditStore(
        history_path=tmp_path / "duplicate_history.csv",
        batch_path=tmp_path / "posted_batches.csv",
        lock_state_path=tmp_path / "posting_locks.json",
    )
    key = branch_lock_key("MMC038", "sheet123")

    lock = store.acquire_branch_lock(lock_key=key, batch_id="batch1", operator_email="operator@example.com", operator_name="Operator")
    with pytest.raises(BranchLockError):
        store.acquire_branch_lock(lock_key=key, batch_id="batch2", operator_email="other@example.com", operator_name="Other")
    released_at = store.release_branch_lock(lock)
    second = store.acquire_branch_lock(lock_key=key, batch_id="batch2", operator_email="other@example.com", operator_name="Other")

    assert released_at
    assert second.batch_id == "batch2"


def test_branch_posting_lock_stale_timeout(tmp_path):
    store = LocalCsvDuplicateAuditStore(
        history_path=tmp_path / "duplicate_history.csv",
        batch_path=tmp_path / "posted_batches.csv",
        lock_state_path=tmp_path / "posting_locks.json",
    )
    key = branch_lock_key("MMC038", "sheet123")
    store.acquire_branch_lock(
        lock_key=key,
        batch_id="batch1",
        operator_email="operator@example.com",
        operator_name="Operator",
        timeout_seconds=-1,
    )
    replacement = store.acquire_branch_lock(lock_key=key, batch_id="batch2", operator_email="other@example.com", operator_name="Other")

    assert replacement.batch_id == "batch2"


def test_duplicate_batch_and_transaction_prevention(tmp_path):
    store = LocalCsvDuplicateAuditStore(
        history_path=tmp_path / "duplicate_history.csv",
        batch_path=tmp_path / "posted_batches.csv",
        lock_state_path=tmp_path / "posting_locks.json",
    )
    records = [
        {
            "Status": "PASSED",
            "Transaction Key": "key1",
            "Account Name": "A",
            "Date": "2026-01-01",
            "Reference": "1 - X",
            "Amount": Decimal("1"),
            "Interest": Decimal("0"),
            "Rebate": Decimal("0"),
            "Actual Collection": Decimal("1"),
        }
    ]

    first = store.record_posted_batch(
        batch_id="batch1",
        operator_email="operator@example.com",
        target_branch_id="MMC038",
        target_tabs=["ACCOUNTS"],
        records=records,
        posted_at="2026-01-01T00:00:00+00:00",
    )
    same_batch = store.record_posted_batch(
        batch_id="batch1",
        operator_email="operator@example.com",
        target_branch_id="MMC038",
        target_tabs=["ACCOUNTS"],
        records=records,
        posted_at="2026-01-01T00:00:01+00:00",
    )
    duplicate_transaction = store.record_posted_batch(
        batch_id="batch2",
        operator_email="operator@example.com",
        target_branch_id="MMC038",
        target_tabs=["ACCOUNTS"],
        records=records,
        posted_at="2026-01-01T00:00:02+00:00",
    )

    assert first == 1
    assert same_batch == 0
    assert duplicate_transaction == 0
    assert store.batch_exists("batch1")
    assert store.existing_transaction_keys(["key1", "missing"]) == {"key1"}


def test_posting_blocked_when_branch_lock_exists(tmp_path):
    store = LocalCsvDuplicateAuditStore(
        history_path=tmp_path / "duplicate_history.csv",
        batch_path=tmp_path / "posted_batches.csv",
        lock_state_path=tmp_path / "posting_locks.json",
    )
    service = SimsoftWorkflowService(duplicate_store=store)
    state = AppState(current_user_email="operator@example.com", operator_name="Operator")
    state.sheet.target_branch_id = "MMC038"
    state.sheet.target_spreadsheet_id = "sheet123"
    key = branch_lock_key("MMC038", "sheet123")
    store.acquire_branch_lock(lock_key=key, batch_id="other", operator_email="other@example.com", operator_name="Other")

    with pytest.raises(BranchLockError):
        service.acquire_posting_lock(state)


def test_posting_blocked_when_validation_state_is_stale():
    service = SimsoftWorkflowService()
    state = AppState(test_mode=True)
    state.sheet.target_branch_id = "MMC038"
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.sheet.active_daily_tab = "1-31"
    state.sheet.accounts_rows = [["old"]]
    state.sheet.receipt_rows = [["r"]]
    state.sheet.daily_rows = [["d"]]
    state.sheet.scr_rows = [["s"]]
    state.posting.validation_snapshot = service.sheet_snapshot(state)
    state.sheet.accounts_rows = [["changed"]]

    with pytest.raises(PermissionError, match="sheet changed"):
        service.ensure_validation_current(state)


def test_posting_gate_ignores_receipt_errors_for_accounts_duplicates():
    service = SimsoftWorkflowService()
    state = AppState(auth_ready=True)
    state.sheet.google_ready = True
    state.sheet.target_branch_id = "MMC075"
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.sheet.active_daily_tab = "1-31"
    state.branch_index = {"MMC075": {"spreadsheet_id": "sheet123"}}
    state.cache.preview = "Fresh"
    state.posting.validation_snapshot = "snapshot"
    state.posting.parsed_df = pd.DataFrame(
        [
            {"Status": "PASSED", "Transaction Key": "postable"},
            {"Status": "PASSED", "Transaction Key": "duplicate-account"},
        ]
    )
    state.posting.accounts_preview_df = pd.DataFrame(
        [
            {"Target Tab": "ACCOUNTS", "Status": "PASSED", "Transaction Key": "postable", "Account Name": "A"},
            {"Target Tab": "ACCOUNTS", "Status": "DUPLICATE", "Transaction Key": "duplicate-account", "Account Name": "B"},
        ]
    )
    state.posting.receipt_preview_df = pd.DataFrame(
        [
            {"Target Tab": "RECIEPT", "Status": "PASSED", "Transaction Key": "postable"},
            {"Target Tab": "RECIEPT", "Status": "ERROR", "Transaction Key": "duplicate-account", "Issue": "RECIEPT Series already has different Date or Amount"},
        ]
    )
    state.posting.daily_preview_df = pd.DataFrame([{"Target Tab": "1-31", "Status": "PASSED", "Transaction Key": "postable"}])
    state.posting.scr_preview_df = pd.DataFrame([{"Target Tab": "SCR VS BR", "Status": "PASSED", "Transaction Key": "postable"}])

    reasons = service.recompute_posting_gate(state)

    assert reasons == []
    assert state.posting.can_post


def test_posting_gate_blocks_receipt_errors_for_postable_accounts():
    service = SimsoftWorkflowService()
    state = AppState(auth_ready=True)
    state.sheet.google_ready = True
    state.sheet.target_branch_id = "MMC075"
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.branch_index = {"MMC075": {"spreadsheet_id": "sheet123"}}
    state.cache.preview = "Fresh"
    state.posting.validation_snapshot = "snapshot"
    state.posting.parsed_df = pd.DataFrame([{"Status": "PASSED", "Transaction Key": "postable"}])
    state.posting.accounts_preview_df = pd.DataFrame([{"Target Tab": "ACCOUNTS", "Status": "PASSED", "Transaction Key": "postable", "Account Name": "A"}])
    state.posting.receipt_preview_df = pd.DataFrame(
        [{"Target Tab": "RECIEPT", "Status": "ERROR", "Transaction Key": "postable", "Issue": "RECIEPT Series already has different Date or Amount"}]
    )

    reasons = service.recompute_posting_gate(state)

    assert not state.posting.can_post
    assert any("RECIEPT" in reason for reason in reasons)


def test_preview_generation_is_cached(monkeypatch):
    import python_backend.services.workflow_service as workflow_service

    service = SimsoftWorkflowService()
    state = AppState(auth_ready=True)
    state.sheet.google_ready = True
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.sheet.active_daily_tab = "1-31"
    state.sheet.accounts_rows = [["ACCOUNT"], ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA"]]
    state.sheet.accounts_headers = HEADERS
    state.sheet.receipt_rows = [["TYPE", "SERIES", "DATE", "AMOUNT"]]
    state.sheet.receipt_headers = ["TYPE", "SERIES", "DATE", "AMOUNT"]
    state.sheet.daily_rows = [["#"]]
    state.sheet.scr_rows = [["SCR DATE", "AMOUNT"], ["02-May-26", ""]]
    state.posting.parsed_df, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row()]), set())
    service._last_parse_key = ("parse-key",)

    calls = {"accounts": 0}

    def fake_accounts(parsed_df, sheet_rows, headers, header_row):
        calls["accounts"] += 1
        return pd.DataFrame([{"Target Tab": "ACCOUNTS", "Status": "PASSED"}]), []

    monkeypatch.setattr(workflow_service, "prepare_accounts_preview", fake_accounts)
    monkeypatch.setattr(workflow_service, "prepare_receipt_preview", lambda *args: (pd.DataFrame([{"Target Tab": "RECIEPT", "Status": "PASSED"}]), []))
    monkeypatch.setattr(workflow_service, "prepare_daily_preview", lambda *args: pd.DataFrame([{"Target Tab": "1-31", "Status": "PASSED"}]))
    monkeypatch.setattr(workflow_service, "prepare_scr_vs_br_updates", lambda *args: (pd.DataFrame([{"Target Tab": "SCR VS BR", "Status": "PASSED"}]), [], []))
    monkeypatch.setattr(service, "write_preview_audit", lambda state: None)

    service.build_previews(state)
    service.build_previews(state)

    assert calls["accounts"] == 1


def test_post_preview_build_skips_review_only_artifacts(monkeypatch):
    import python_backend.services.workflow_service as workflow_service

    service = SimsoftWorkflowService()
    state = AppState(auth_ready=True)
    state.sheet.google_ready = True
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.sheet.active_daily_tab = "1-31"
    state.sheet.accounts_rows = [["ACCOUNT"], ["MMC042-01167R / RICHIELLE ABEJUELLA DARIA"]]
    state.sheet.accounts_headers = HEADERS
    state.sheet.receipt_rows = [["TYPE", "SERIES", "DATE", "AMOUNT"]]
    state.sheet.receipt_headers = ["TYPE", "SERIES", "DATE", "AMOUNT"]
    state.sheet.daily_rows = [["#"]]
    state.sheet.scr_rows = [["SCR DATE", "AMOUNT"], ["02-May-26", ""]]
    state.posting.parsed_df, _ = parse_and_validate_simsoft(pd.DataFrame([simsoft_row()]), set())
    service._last_parse_key = ("parse-key",)

    calls = {"layout": 0, "ai": 0, "audit": 0}
    monkeypatch.setattr(workflow_service, "prepare_accounts_preview", lambda *args: (pd.DataFrame([{"Target Tab": "ACCOUNTS", "Status": "PASSED"}]), []))
    monkeypatch.setattr(workflow_service, "prepare_receipt_preview", lambda *args: (pd.DataFrame([{"Target Tab": "RECIEPT", "Status": "PASSED"}]), []))
    monkeypatch.setattr(workflow_service, "prepare_daily_preview", lambda *args: pd.DataFrame([{"Target Tab": "1-31", "Status": "PASSED"}]))
    monkeypatch.setattr(workflow_service, "prepare_scr_vs_br_updates", lambda *args: (pd.DataFrame([{"Target Tab": "SCR VS BR", "Status": "PASSED"}]), [], []))

    def fake_layout(state):
        calls["layout"] += 1
        return {}

    def fake_ai(context):
        calls["ai"] += 1
        return {}

    def fake_audit(state):
        calls["audit"] += 1
        return None

    monkeypatch.setattr(workflow_service, "build_sheet_layout_previews", fake_layout)
    monkeypatch.setattr(workflow_service, "resolve_posting_with_gemini", fake_ai)
    monkeypatch.setattr(service, "write_preview_audit", fake_audit)

    service.build_previews(state, include_review_artifacts=False)

    assert calls == {"layout": 0, "ai": 0, "audit": 0}
    assert state.posting.sheet_layouts == {}
    assert state.posting.ai_resolver == {}


def test_audit_log_records_google_actor_email(tmp_path):
    preview = pd.DataFrame(
        [
            {
                "Target Tab": "ACCOUNTS",
                "Status": "PASSED",
                "Account Name": "MMC038-001 / TEST USER",
                "Transaction Key": "key1",
            }
        ]
    )

    path = write_audit_log(
        preview,
        "batch1",
        "https://docs.google.com/spreadsheets/d/sheet123/edit",
        "simsoft.xlsx",
        ["ACCOUNTS"],
        log_dir=tmp_path,
        auth_metadata={
            "auth_mode": AUTH_MODE_USER_OAUTH,
            "google_actor_email": "operator@example.com",
            "operator_email": "operator@example.com",
            "posted_by_email": "operator@example.com",
            "posted_by_google_user": "operator@example.com",
            "token_user_email": "operator@example.com",
            "operator_name": "Operator",
            "started_at": "2026-01-01T00:00:00+00:00",
            "posted_at": "2026-01-01T00:01:00+00:00",
            "lock_acquired_at": "2026-01-01T00:00:30+00:00",
            "lock_released_at": "2026-01-01T00:01:05+00:00",
            "row_count": 1,
            "posted_tabs": "ACCOUNTS",
            "errors": "",
            "duplicate_count": 0,
        },
    )

    audit_df = pd.read_csv(path)
    assert audit_df.loc[0, "auth_mode"] == AUTH_MODE_USER_OAUTH
    assert audit_df.loc[0, "google_actor_email"] == "operator@example.com"
    assert audit_df.loc[0, "posted_by_google_user"] == "operator@example.com"
    assert audit_df.loc[0, "operator_name"] == "Operator"
    assert audit_df.loc[0, "lock_acquired_at"] == "2026-01-01T00:00:30+00:00"
    assert audit_df.loc[0, "row_count"] == 1


def test_audit_log_records_swipe_confirmation_method(tmp_path):
    preview = pd.DataFrame([{"Target Tab": "ACCOUNTS", "Status": "PASSED", "Transaction Key": "key1"}])

    path = write_audit_log(
        preview,
        "batch-swipe",
        "https://docs.google.com/spreadsheets/d/sheet123/edit",
        "simsoft.xlsx",
        ["ACCOUNTS"],
        log_dir=tmp_path,
        auth_metadata={
            "confirmation_method": "swipe_to_post",
            "validation_snapshot_id": "snapshot-1",
            "preview_generated_at": "2026-01-01T00:00:00+00:00",
            "branch_lock_id": "MMC038|sheet123",
        },
    )

    audit_df = pd.read_csv(path)
    assert audit_df.loc[0, "confirmation_method"] == "swipe_to_post"
    assert audit_df.loc[0, "validation_snapshot_id"] == "snapshot-1"
    assert audit_df.loc[0, "branch_lock_id"] == "MMC038|sheet123"


def test_cloud_ready_local_store_abstractions(tmp_path):
    duplicate_store = LocalDuplicateStore(tmp_path / "duplicate_history.csv")
    duplicate_store.add_transaction_keys(
        [
            {
                "Status": "PASSED",
                "Transaction Key": "key-cloud",
                "Account Name": "A",
                "Date": "2026-01-01",
                "Reference": "1 - X",
                "Amount": Decimal("1"),
                "Interest": Decimal("0"),
                "Rebate": Decimal("0"),
                "Actual Collection": Decimal("1"),
            }
        ],
        "batch-cloud",
        ["ACCOUNTS"],
    )
    assert duplicate_store.has_transaction_key("key-cloud")
    assert duplicate_store.existing_transaction_keys(["key-cloud", "missing"]) == {"key-cloud"}

    branch_store = LocalBranchIndexStore(tmp_path / "branch_cache.json", ttl_seconds=60)
    branch_store.set("folder-key", {"MMC038": {"branch_name": "POZORRUBIO", "spreadsheet_id": "sheet123"}})
    assert branch_store.get("folder-key")["MMC038"]["spreadsheet_id"] == "sheet123"
    branch_store.invalidate("folder-key")
    assert branch_store.get("folder-key") is None

    ibp_store = LocalIBPLookupCacheStore()
    ibp_store.set_account_lookup("sheet123|MMC038-02607", {"status": "OK"})
    ibp_store.set_branch_index("sheet123", {"rows": []})
    assert ibp_store.get_account_lookup("sheet123|MMC038-02607") == {"status": "OK"}
    assert ibp_store.get_branch_index("sheet123") == {"rows": []}
    ibp_store.clear()
    assert ibp_store.get_account_lookup("sheet123|MMC038-02607") is None


def test_swipe_post_gate_ready_and_locked_states():
    assert can_swipe_to_post(
        connection_ok=True,
        file_valid=True,
        has_blocking_errors=False,
        live_posting_enabled=True,
        auth_signed_in=True,
        preview_fresh=True,
        target_branch_selected=True,
        folder_scan_complete=True,
        branch_unlocked=True,
    )
    assert not can_swipe_to_post(
        connection_ok=True,
        file_valid=True,
        has_blocking_errors=False,
        live_posting_enabled=True,
        auth_signed_in=True,
        preview_fresh=False,
        target_branch_selected=True,
        folder_scan_complete=True,
        branch_unlocked=True,
    )
