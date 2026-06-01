from __future__ import annotations

from typing import Any

import pandas as pd

from .accounts import build_header_map, cell_value
from .accounts import decimal_to_display, display_sheet_date
from .parser import normalize_text


RECEIPT_HEADERS = ["Series", "Type", "Date", "Amount"]
RECEIPT_TYPE = "CR"
CANCELED_AMOUNT = "CANCELLED"
RECEIPT_BLOCK_SIZE = 50


def receipt_block_start(series: int) -> int:
    return ((series - 1) // RECEIPT_BLOCK_SIZE) * RECEIPT_BLOCK_SIZE + 1


def receipt_block_end(series: int) -> int:
    return receipt_block_start(series) + RECEIPT_BLOCK_SIZE - 1


def skipped_receipt_series(previous_series: int, next_series: int) -> list[int]:
    if receipt_block_start(previous_series) != receipt_block_start(next_series):
        return list(range(previous_series + 1, receipt_block_end(previous_series) + 1))
    return list(range(previous_series + 1, next_series))


def skipped_receipt_series_within_block(series_numbers: list[int]) -> list[int]:
    skipped: list[int] = []
    for previous_series, next_series in zip(series_numbers, series_numbers[1:]):
        skipped.extend(range(previous_series + 1, next_series))
    return skipped


def canonical_receipt_header(value: Any) -> str:
    return " ".join(normalize_text(value).upper().split())


def _receipt_block_has_data_after_header(sheet_rows: list[list[Any]], row_index: int, col_index: int) -> bool:
    for next_row in sheet_rows[row_index + 1 : row_index + 51]:
        type_value = canonical_receipt_header(cell_value(next_row, col_index))
        series_value = normalize_text(cell_value(next_row, col_index + 1))
        if type_value not in {"", "TYPE"}:
            return True
        if series_value.isdigit():
            return True
    return False


def find_receipt_blocks(sheet_rows: list[list[Any]]) -> list[dict[str, int]]:
    blocks: list[dict[str, int]] = []
    for row_index, row in enumerate(sheet_rows):
        for col_index in range(max(len(row) - 3, 0)):
            labels = [canonical_receipt_header(cell_value(row, col_index + offset)) for offset in range(4)]
            if labels != ["TYPE", "SERIES", "DATE", "AMOUNT"]:
                continue
            previous_same_column = [block for block in blocks if block["type_col"] == col_index]
            if previous_same_column and row_index <= previous_same_column[-1]["header_row_index"] + RECEIPT_BLOCK_SIZE:
                continue
            blocks.append(
                {
                    "header_row_index": row_index,
                    "type_col": col_index,
                    "series_col": col_index + 1,
                    "date_col": col_index + 2,
                    "amount_col": col_index + 3,
                }
            )
    return blocks


def build_series_index(sheet_rows: list[list[Any]], headers: list[str], header_row: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    blocks = find_receipt_blocks(sheet_rows)
    if not blocks:
        header_map = build_header_map(headers, RECEIPT_HEADERS)
        blocks = [
            {
                "header_row_index": header_row - 1,
                "type_col": header_map["TYPE"],
                "series_col": header_map["SERIES"],
                "date_col": header_map["DATE"],
                "amount_col": header_map["AMOUNT"],
            }
        ]

    index: dict[str, dict[str, Any]] = {}
    block_infos: list[dict[str, Any]] = []
    sorted_blocks = sorted(blocks, key=lambda item: (item["header_row_index"], item["type_col"]))
    for block in sorted_blocks:
        next_same_column_header = next(
            (
                candidate["header_row_index"]
                for candidate in sorted_blocks
                if candidate["type_col"] == block["type_col"] and candidate["header_row_index"] > block["header_row_index"]
            ),
            len(sheet_rows),
        )
        block_info = {
            "header_row_index": block["header_row_index"],
            "type_col": block["type_col"],
            "series_col": block["series_col"],
            "date_col": block["date_col"],
            "amount_col": block["amount_col"],
            "series_starts": set[int](),
            "placeholders": [],
        }
        for zero_based_idx, row in enumerate(sheet_rows[block["header_row_index"] + 1 : next_same_column_header], start=block["header_row_index"] + 2):
            if canonical_receipt_header(cell_value(row, block["type_col"])) == "TYPE":
                continue
            series = normalize_text(cell_value(row, block["series_col"]))
            if series:
                clean_series = series.lstrip("0")
                if clean_series:
                    index[clean_series] = {
                        "row_number": zero_based_idx,
                        "values": row,
                        "type_col": block["type_col"],
                        "series_col": block["series_col"],
                        "date_col": block["date_col"],
                        "amount_col": block["amount_col"],
                    }
                    if clean_series.isdigit():
                        block_info["series_starts"].add(receipt_block_start(int(clean_series)))
                continue
            if normalize_text(cell_value(row, block["type_col"])) == "":
                block_info["placeholders"].append(
                    {
                        "row_number": zero_based_idx,
                        "values": row,
                        "type_col": block["type_col"],
                        "series_col": block["series_col"],
                        "date_col": block["date_col"],
                        "amount_col": block["amount_col"],
                    }
                )
        block_infos.append(block_info)
    return index, block_infos


def _find_placeholder_for_series(block_infos: list[dict[str, Any]], series: int) -> dict[str, Any] | None:
    desired_start = receipt_block_start(series)
    exact_matches = [block for block in block_infos if desired_start in block["series_starts"] and block["placeholders"]]
    if exact_matches:
        return exact_matches[0]["placeholders"].pop(0)

    if len([block for block in block_infos if block["placeholders"]]) == 1:
        block = next(block for block in block_infos if block["placeholders"])
        return block["placeholders"].pop(0)

    return None


def prepare_receipt_preview(parsed_df: pd.DataFrame, branch_name: str, sheet_rows: list[list[Any]] | None = None, headers: list[str] | None = None, header_row: int = 1) -> tuple[pd.DataFrame, list[str]]:
    index: dict[str, dict[str, Any]] = {}
    block_infos: list[dict[str, Any]] = []
    if sheet_rows is not None and headers is not None:
        try:
            index, block_infos = build_series_index(sheet_rows, headers, header_row)
        except ValueError as exc:
            return pd.DataFrame(), [str(exc)]

    records = []
    recorded_series: set[str] = set()
    for row in parsed_df.to_dict("records"):
        series = str(row.get("OR Number", ""))
        status = row.get("Status", "PASSED")
        issue = row.get("Issue", "")
        target = index.get(series) if index else None
        if index and status == "PASSED" and not target and normalize_text(series).isdigit():
            placeholder = _find_placeholder_for_series(block_infos, int(series))
            if placeholder:
                target = placeholder
                status = "PASSED"
                issue = "RECIEPT Series missing; inserted as canceled"
            else:
                status, issue = "ERROR", "Series not found in RECIEPT"
        if target and status == "PASSED":
            existing_date = normalize_text(cell_value(target["values"], target["date_col"]))
            existing_amount = normalize_text(cell_value(target["values"], target["amount_col"]))
            new_date = display_sheet_date(row.get("Date"))
            new_amount = f"{row.get('Actual Collection'):.2f}"
            if existing_date and existing_amount and existing_date == new_date and existing_amount == new_amount:
                status, issue = "DUPLICATE", "RECIEPT Series already has same Date and Amount"
            elif existing_date or existing_amount:
                status, issue = "ERROR", "RECIEPT Series already has different Date or Amount"
        amount_value = CANCELED_AMOUNT if issue == "RECIEPT Series missing; inserted as canceled" else row.get("Actual Collection")
        records.append(
            {
                "Target Tab": "RECIEPT",
                "Target Row": target["row_number"] if target else "",
                "Type": RECEIPT_TYPE,
                "Series": series,
                "Date": row.get("Date"),
                "Amount": amount_value,
                "Type Col": target["type_col"] + 1 if target else "",
                "Series Col": target["series_col"] + 1 if target else "",
                "Date Col": target["date_col"] + 1 if target else "",
                "Amount Col": target["amount_col"] + 1 if target else "",
                "Status": status,
                "Issue": issue,
                "Transaction Key": row.get("Transaction Key"),
            }
        )
        recorded_series.add(series)
    if index:
        passed_rows = parsed_df[parsed_df["Status"] == "PASSED"] if "Status" in parsed_df else parsed_df
        for receipt_date, group in passed_rows.groupby("Date"):
            series_by_block: dict[int, list[int]] = {}
            for value in group["OR Number"]:
                if normalize_text(value).isdigit():
                    series = int(value)
                    block_start = receipt_block_start(series)
                    series_by_block.setdefault(block_start, []).append(series)
            for series_numbers in series_by_block.values():
                series_numbers = sorted(set(series_numbers))
                # Cancel missing ORs between passed series values and any existing blank sheet rows below them.
                for skipped_series in skipped_receipt_series_within_block(series_numbers):
                    series = str(skipped_series)
                    if series in recorded_series:
                        continue
                    target = index.get(series)
                    status = "PASSED"
                    issue = "Skipped OR marked canceled"
                    if not target:
                        placeholder = _find_placeholder_for_series(block_infos, int(series))
                        if placeholder:
                            target = placeholder
                        else:
                            status, issue = "ERROR", "Skipped RECIEPT Series not found"
                    if target and status == "PASSED":
                        existing_date = normalize_text(cell_value(target["values"], target["date_col"]))
                        existing_amount = normalize_text(cell_value(target["values"], target["amount_col"]))
                        new_date = display_sheet_date(receipt_date)
                        if existing_date and existing_amount and existing_date == new_date and existing_amount.upper() == CANCELED_AMOUNT.upper():
                            issue = "Skipped OR already canceled"
                        elif existing_date or existing_amount:
                            status, issue = "ERROR", "Skipped RECIEPT Series already has Date or Amount"
                    records.append(
                        {
                            "Target Tab": "RECIEPT",
                            "Target Row": target["row_number"] if target else "",
                            "Type": RECEIPT_TYPE,
                            "Series": series,
                            "Date": receipt_date,
                            "Amount": CANCELED_AMOUNT,
                            "Type Col": target["type_col"] + 1 if target else "",
                            "Date Col": target["date_col"] + 1 if target else "",
                            "Amount Col": target["amount_col"] + 1 if target else "",
                            "Status": status,
                            "Issue": issue,
                            "Transaction Key": "",
                        }
                    )
                    recorded_series.add(series)

                parsed_series_set = set(series_numbers)
                existing_series = sorted(
                    int(series)
                    for series in index
                    if receipt_block_start(int(series)) == receipt_block_start(series_numbers[0]) and int(series) not in parsed_series_set
                )
                for series in existing_series:
                    if str(series) in recorded_series:
                        continue
                    if not any(passed_series > series for passed_series in series_numbers):
                        continue
                    target = index.get(str(series))
                    if not target:
                        continue
                    existing_date = normalize_text(cell_value(target["values"], target["date_col"]))
                    existing_amount = normalize_text(cell_value(target["values"], target["amount_col"]))
                    if existing_date or existing_amount:
                        continue
                    records.append(
                        {
                            "Target Tab": "RECIEPT",
                            "Target Row": target["row_number"],
                            "Type": RECEIPT_TYPE,
                            "Series": str(series),
                            "Date": receipt_date,
                            "Amount": CANCELED_AMOUNT,
                            "Type Col": target["type_col"] + 1,
                            "Date Col": target["date_col"] + 1,
                            "Amount Col": target["amount_col"] + 1,
                            "Status": "PASSED",
                            "Issue": "Skipped OR marked canceled",
                            "Transaction Key": "",
                        }
                    )
                    recorded_series.add(str(series))
    return pd.DataFrame(records), []


def prepare_receipt_updates(receipt_preview: pd.DataFrame, headers: list[str]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    passed = receipt_preview[receipt_preview["Status"] == "PASSED"] if "Status" in receipt_preview else pd.DataFrame()
    for row in passed.to_dict("records"):
        target_row = int(row["Target Row"])
        if row.get("Type Col") and row.get("Date Col") and row.get("Amount Col"):
            type_col = int(row["Type Col"])
            raw_series_col = row.get("Series Col")
            if raw_series_col is not None and raw_series_col != "" and not (isinstance(raw_series_col, float) and pd.isna(raw_series_col)):
                series_col = int(raw_series_col)
            else:
                series_col = None
            date_col = int(row["Date Col"])
            amount_col = int(row["Amount Col"])
        else:
            header_map = build_header_map(headers, RECEIPT_HEADERS)
            type_col = header_map["TYPE"] + 1
            series_col = header_map["SERIES"] + 1
            date_col = header_map["DATE"] + 1
            amount_col = header_map["AMOUNT"] + 1
        entry = [
            {"row": target_row, "col": type_col, "value": row["Type"]},
        ]
        if series_col is not None:
            entry.append({"row": target_row, "col": series_col, "value": row["Series"]})
        entry.extend(
            [
                {"row": target_row, "col": date_col, "value": display_sheet_date(row["Date"])},
                {"row": target_row, "col": amount_col, "value": decimal_to_display(row["Amount"])},
            ]
        )
        updates.extend(entry)
    return updates
