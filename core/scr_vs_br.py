from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from .accounts import append_formula_terms, append_line_break, cell_value, decimal_to_display, decimal_to_formula_term
from .parser import normalize_text, parse_amount, parse_date


BLOCK_NAMES = ["BRANCH RECEIPT 1", "BRANCH RECEIPT 2", "COLLECTOR RECEIPT 2", "COLLECTOR RECEIPT 3"]
SCR_TAB = "SCR VS BR"
SCR_DATE_COL = 1
SCR_AMOUNT_COL = 2
RECEIPT_BLOCKS = [
    {"Block": "BRANCH RECEIPT", "from_col": 4, "to_col": 5, "amount_col": 6},
    {"Block": "COLLECTOR RECEIPT 1", "from_col": 7, "to_col": 8, "amount_col": 9},
    {"Block": "COLLECTOR RECEIPT 2", "from_col": 10, "to_col": 11, "amount_col": 12},
    {"Block": "COLLECTOR RECEIPT 3", "from_col": 13, "to_col": 14, "amount_col": 15},
]
EMPTY_VALUES = {"", "-", "\u2013", "\u2014", "â€“", "â€”"}
SKIPPED_OR_GAP_LIMIT = 10
RECEIPT_BLOCK_SIZE = 50

# SCR VS BR placement rules
#
# 1. RECIEPT scan is the basis for OR block status. A receipt block is closed
#    when its ending OR is posted/cancelled, or all missing ORs up to the block
#    end are cancelled. Otherwise it is open.
# 2. If the OR is continueable and the same receipt block is still open,
#    continue the SCR VS BR range.
# 3. If a closed OR block is followed by a new open OR block and the new OR is
#    continueable, merge it with the closed block.
# 4. Other Day Rule: if the previous OR block is closed and the new OR is not
#    continueable, the new OR may follow its own path only when no other OR in
#    the same batch continues that closed block. If nothing continues that
#    closed block, write the non-continueable OR under it with a line break.
# 5. If there is no closed block to follow, place the new open OR block in the
#    first safe available SCR VS BR space, using previous dates to choose the
#    correct column.
# 6. Always follow OR sequence: never put a lower OR under a block whose
#    sequence has already passed it, and never silently post a duplicate OR.
#
# In short: RECIEPT tells open/closed; SCR VS BR sequence chooses the path.


def parse_or_range(or_text: Any) -> dict[str, Any]:
    text = normalize_text(or_text).replace(",", "")
    if not text:
        return {"valid": False, "start": None, "end": None, "prefix": "", "text": ""}
    parts = [part.strip() for part in text.replace("\r", "\n").split("\n") if part.strip()]
    if len(parts) > 1:
        parsed_parts = [parse_or_range(part) for part in parts]
        valid_parts = [part for part in parsed_parts if part["valid"]]
        if not valid_parts or len(valid_parts) != len(parsed_parts):
            return {"valid": False, "start": None, "end": None, "prefix": "", "text": text}
        return {
            "valid": True,
            "start": valid_parts[0]["start"],
            "end": valid_parts[-1]["end"],
            "prefix": valid_parts[-1].get("prefix", ""),
            "text": text,
        }
    import re

    match = re.match(r"^\s*([A-Za-z-]*?)\s*(\d+)(?:\s*[-–—]\s*([A-Za-z-]*?)\s*(\d+))?\s*$", text)
    if not match:
        return {"valid": False, "start": None, "end": None, "prefix": "", "text": text}
    prefix, start_text, end_prefix, end_text = match.groups()
    start = int(start_text)
    end = int(end_text) if end_text else start
    if end < start:
        return {"valid": False, "start": None, "end": None, "prefix": prefix or "", "text": text}
    if end_prefix and prefix and end_prefix != prefix:
        return {"valid": False, "start": None, "end": None, "prefix": prefix or "", "text": text}
    return {"valid": True, "start": start, "end": end, "prefix": prefix or end_prefix or "", "text": text}


def get_or_start(or_text: Any) -> int | None:
    parsed = parse_or_range(or_text)
    return int(parsed["start"]) if parsed["valid"] else None


def get_or_end(or_text: Any) -> int | None:
    parsed = parse_or_range(or_text)
    return int(parsed["end"]) if parsed["valid"] else None


def is_continueable_or(previous_or: Any, new_or: Any) -> bool:
    # Continueable OR: the new start must directly follow the previous OR/range end.
    previous = parse_or_range(previous_or)
    new = parse_or_range(new_or)
    if not previous["valid"] or not new["valid"]:
        return False
    if previous.get("prefix") and new.get("prefix") and previous["prefix"] != new["prefix"]:
        return False
    return int(new["start"]) == int(previous["end"]) + 1


def is_same_collection_day(previous_date: Any, new_date: Any) -> bool:
    return bool(previous_date and new_date and normalize_text(previous_date) == normalize_text(new_date))


def is_other_collection_day(previous_date: Any, new_date: Any) -> bool:
    return bool(previous_date and new_date and normalize_text(previous_date) != normalize_text(new_date))


def is_or_closed(or_group: Any) -> bool:
    if isinstance(or_group, dict):
        if "done" in or_group:
            return bool(or_group["done"])
        if "closed_start" in or_group and "closed_end" in or_group:
            return or_group.get("closed_start") is not None and or_group.get("closed_end") is not None
    return False


def has_available_scrvsbr_space(context: Any) -> bool:
    if isinstance(context, dict):
        blocks = context.get("block_scores")
        if isinstance(blocks, list):
            new_or_text = normalize_text(context.get("new_or_text", ""))
            if new_or_text:
                return any(
                    bool(block.get("empty")) and _empty_block_respects_previous_or(block, new_or_text)
                    for block in blocks
                )
            return any(bool(block.get("empty")) for block in blocks)
    return False


def append_or_normally(previous_or_text: Any, new_or_text: Any) -> str:
    previous = parse_or_range(previous_or_text)
    new = parse_or_range(new_or_text)
    if not previous["valid"] or not new["valid"]:
        return append_line_break(previous_or_text, new_or_text)
    prefix = previous.get("prefix") or new.get("prefix") or ""
    start = int(previous["start"])
    end = int(new["end"])
    if start == end:
        return f"{prefix}{start}"
    return f"{prefix}{start}-{prefix if prefix else ''}{end}"


def append_or_with_breakline(previous_or_text: Any, new_or_text: Any) -> str:
    return append_line_break(previous_or_text, new_or_text)


def _append_scr_line(existing: Any, new_value: Any, preserve_blank: bool = False) -> str:
    existing_text = normalize_text(existing)
    new_text = normalize_text(new_value)
    if not existing_text:
        return new_text
    if not new_text and not preserve_blank:
        return existing_text
    return f"{existing_text}\n{new_text}"


# Compatibility aliases for the rule names in the implementation request.
parseOrRange = parse_or_range
getOrStart = get_or_start
getOrEnd = get_or_end
isContinueableOr = is_continueable_or
isSameCollectionDay = is_same_collection_day
isOtherCollectionDay = is_other_collection_day
isOrClosed = is_or_closed
hasAvailableScrvsbrSpace = has_available_scrvsbr_space
appendOrNormally = append_or_normally
appendOrWithBreakline = append_or_with_breakline


def build_receipt_blocks(or_amounts: dict[int, Decimal], previous_ors: dict[str, int]) -> tuple[list[dict[str, Any]], list[int]]:
    remaining = dict(sorted(or_amounts.items()))
    blocks: list[dict[str, Any]] = []
    used: set[int] = set()
    for block_name in BLOCK_NAMES:
        last_or = previous_ors.get(block_name)
        collected: list[int] = []
        if last_or is not None:
            next_or = last_or + 1
            while next_or in remaining:
                collected.append(next_or)
                used.add(next_or)
                del remaining[next_or]
                next_or += 1
        amount = sum((or_amounts[or_no] for or_no in collected), Decimal("0.00"))
        blocks.append(
            {
                "Block": block_name,
                "FROM": collected[0] if collected else "",
                "TO": collected[-1] if len(collected) > 1 else "",
                "AMOUNT": amount,
                "ORs": collected,
            }
        )
    return blocks, sorted(set(or_amounts) - used)


def prepare_scr_vs_br_preview(parsed_df: pd.DataFrame, previous_ors: dict[str, int] | None = None) -> pd.DataFrame:
    previous_ors = previous_ors or {}
    records = []
    for scr_date, group in parsed_df.groupby("Date", dropna=False):
        or_amounts = {
            int(row["OR Number"]): row["Actual Collection"]
            for row in group.to_dict("records")
            if str(row.get("OR Number", "")).isdigit()
        }
        blocks, unused = build_receipt_blocks(or_amounts, previous_ors)
        block_total = sum((block["AMOUNT"] for block in blocks), Decimal("0.00"))
        scr_amount = sum(or_amounts.values(), Decimal("0.00"))
        variance = (scr_amount - block_total).quantize(Decimal("0.01"))
        status = "PASSED" if variance == 0 and not unused else "ERROR"
        issue = "" if status == "PASSED" else "SCR receipt block variance or unassigned OR"
        for block in blocks:
            records.append(
                {
                    "Target Tab": SCR_TAB,
                    "SCR DATE": scr_date,
                    "SCR AMOUNT": scr_amount,
                    **block,
                    "Variance": variance,
                    "Unused ORs": ", ".join(map(str, unused)),
                    "Status": status,
                    "Issue": issue,
                }
            )
    return pd.DataFrame(records)


def _parse_ors(value: Any) -> list[int]:
    text = normalize_text(value).replace(",", "")
    if not text:
        return []
    ors: list[int] = []
    for part in text.replace("\r", "\n").split("\n"):
        cleaned = part.strip()
        if not cleaned or cleaned in EMPTY_VALUES:
            continue
        try:
            ors.append(int(float(cleaned)))
        except ValueError:
            continue
    return ors


def _row_date(value: Any) -> str:
    text = normalize_text(value)
    if not text or text.upper() == "TOTAL":
        return ""
    try:
        return parse_date(text)
    except ValueError:
        return ""


def find_scr_date_rows(sheet_rows: list[list[Any]]) -> dict[str, int]:
    date_rows: dict[str, int] = {}
    for row_number, row in enumerate(sheet_rows, start=1):
        iso_date = _row_date(cell_value(row, SCR_DATE_COL - 1))
        if iso_date:
            date_rows[iso_date] = row_number
    return date_rows


def contiguous_or_ranges(or_amounts: dict[int, Decimal]) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    current: list[int] = []
    skipped: list[int] = []
    for or_number in sorted(or_amounts):
        if not current:
            current.append(or_number)
            continue
        gap = or_number - current[-1]
        if gap == 1:
            current.append(or_number)
            continue
        if 1 < gap <= SKIPPED_OR_GAP_LIMIT + 1:
            skipped.extend(range(current[-1] + 1, or_number))
            current.append(or_number)
            continue
        amount = sum((or_amounts[number] for number in current), Decimal("0.00"))
        ranges.append({"FROM": current[0], "TO": current[-1], "AMOUNT": amount, "ORs": current, "Skipped ORs": skipped, "OR Amounts": {number: or_amounts[number] for number in current}})
        current = [or_number]
        skipped = []
    if current:
        amount = sum((or_amounts[number] for number in current), Decimal("0.00"))
        ranges.append({"FROM": current[0], "TO": current[-1], "AMOUNT": amount, "ORs": current, "Skipped ORs": skipped, "OR Amounts": {number: or_amounts[number] for number in current}})
    return ranges


def _latest_or_before_row(sheet_rows: list[list[Any]], target_row: int, from_col: int, to_col: int) -> int | None:
    latest: int | None = None
    for row in sheet_rows[: max(target_row - 1, 0)]:
        candidates = [*_parse_ors(cell_value(row, from_col - 1)), *_parse_ors(cell_value(row, to_col - 1))]
        candidate = max(candidates) if candidates else None
        if candidate is not None:
            latest = candidate
    return latest


def _previous_or_text_before_row(sheet_rows: list[list[Any]], target_row: int, from_col: int, to_col: int) -> str:
    previous_group = _previous_or_group_before_row(sheet_rows, target_row, from_col, to_col)
    return normalize_text(previous_group.get("text", ""))


def _last_scr_or_group_closed(from_value: Any, to_value: Any) -> bool:
    from_lines = [line for line in normalize_text(from_value).replace("\r", "\n").split("\n") if normalize_text(line)]
    to_lines = [line for line in normalize_text(to_value).replace("\r", "\n").split("\n") if normalize_text(line)]
    if not from_lines or len(to_lines) < len(from_lines):
        return False
    last_to = normalize_text(to_lines[-1])
    return bool(last_to and last_to not in EMPTY_VALUES and parse_or_range(last_to)["valid"])


def _previous_or_group_before_row(sheet_rows: list[list[Any]], target_row: int, from_col: int, to_col: int) -> dict[str, Any]:
    for row in reversed(sheet_rows[: max(target_row - 1, 0)]):
        previous_text = _last_scr_or_group(cell_value(row, from_col - 1), cell_value(row, to_col - 1))
        if parse_or_range(previous_text)["valid"]:
            return {
                "text": previous_text,
                "closed": _last_scr_or_group_closed(cell_value(row, from_col - 1), cell_value(row, to_col - 1)),
            }
    return {"text": "", "closed": False}


def _block_amount_value(existing: Any, or_amounts: list[Decimal]) -> str:
    existing_text = normalize_text(existing)
    if normalize_text(existing_text) in EMPTY_VALUES:
        if len(or_amounts) == 1:
            return decimal_to_display(or_amounts[0])
        return "=" + "+".join(decimal_to_formula_term(amount) for amount in or_amounts)

    if existing_text.startswith("="):
        return append_formula_terms(existing_text, or_amounts)

    if "\n" in existing_text:
        existing_terms = [normalize_text(line) for line in existing_text.splitlines() if normalize_text(line)]
        if existing_terms:
            formula = "=" + "+".join(existing_terms)
            return append_formula_terms(formula, or_amounts)

    return append_formula_terms(existing_text, or_amounts)


def _block_is_empty(row: list[Any], block: dict[str, Any]) -> bool:
    return not any(
        normalize_text(cell_value(row, col - 1)) not in EMPTY_VALUES
        for col in [block["from_col"], block["to_col"], block["amount_col"]]
    )


def _block_existing_ors(row: list[Any], block: dict[str, Any]) -> set[int]:
    return {
        *_parse_ors(cell_value(row, block["from_col"] - 1)),
        *_parse_ors(cell_value(row, block["to_col"] - 1)),
    }


def _block_has_closed_range(row: list[Any], block: dict[str, Any]) -> bool:
    from_values = _parse_ors(cell_value(row, block["from_col"] - 1))
    to_values = _parse_ors(cell_value(row, block["to_col"] - 1))
    return len(from_values) == 1 and len(to_values) == 1


def _range_already_covered(existing_from: Any, existing_to: Any, or_numbers: list[int]) -> bool:
    from_values = _parse_ors(existing_from)
    to_values = _parse_ors(existing_to)
    if len(from_values) != 1:
        return False
    start = from_values[0]
    end = to_values[0] if len(to_values) == 1 else start
    low, high = sorted((start, end))
    return all(low <= int(or_number) <= high for or_number in or_numbers)


def _range_overlaps(existing_from: Any, existing_to: Any, or_numbers: list[int]) -> bool:
    from_values = _parse_ors(existing_from)
    to_values = _parse_ors(existing_to)
    if len(from_values) != 1 or not or_numbers:
        return False
    start = from_values[0]
    end = to_values[0] if len(to_values) == 1 else start
    low, high = sorted((start, end))
    return any(low <= int(or_number) <= high for or_number in or_numbers)


def _range_is_inner_duplicate(existing_from: Any, existing_to: Any, or_numbers: list[int]) -> bool:
    from_values = _parse_ors(existing_from)
    to_values = _parse_ors(existing_to)
    if len(from_values) != 1 or not or_numbers:
        return False
    start = from_values[0]
    end = to_values[0] if len(to_values) == 1 else start
    low, high = sorted((start, end))
    numbers = [int(number) for number in or_numbers]
    return all(low <= number <= high for number in numbers) and not any(number in {low, high} for number in numbers)


def _or_range_text(start_or: Any, end_or: Any = "") -> str:
    start_text = normalize_text(start_or)
    end_text = normalize_text(end_or)
    if not start_text:
        return ""
    if not end_text or end_text == start_text:
        return start_text
    return f"{start_text}-{end_text}"


def _last_scr_or_group(from_value: Any, to_value: Any) -> str:
    from_lines = [line for line in normalize_text(from_value).replace("\r", "\n").split("\n") if normalize_text(line)]
    to_lines = [line for line in normalize_text(to_value).replace("\r", "\n").split("\n") if normalize_text(line)]
    if not from_lines:
        return ""
    last_from = from_lines[-1]
    last_to = to_lines[-1] if len(to_lines) >= len(from_lines) else ""
    return _or_range_text(last_from, last_to)


def _replace_last_scr_or_group(from_value: Any, to_value: Any, merged_text: str) -> tuple[str, str]:
    parsed = parse_or_range(merged_text)
    if not parsed["valid"]:
        return normalize_text(from_value), normalize_text(to_value)
    from_lines = [line for line in normalize_text(from_value).replace("\r", "\n").split("\n") if normalize_text(line)]
    to_lines = [line for line in normalize_text(to_value).replace("\r", "\n").split("\n") if normalize_text(line)]
    if not from_lines:
        return normalize_text(parsed["start"]), normalize_text(parsed["end"] if parsed["end"] != parsed["start"] else "")
    from_lines[-1] = normalize_text(parsed["start"])
    if int(parsed["end"]) == int(parsed["start"]):
        if len(to_lines) >= len(from_lines):
            to_lines[-1] = ""
    elif len(to_lines) >= len(from_lines):
        to_lines[-1] = normalize_text(parsed["end"])
    else:
        to_lines.append(normalize_text(parsed["end"]))
    return "\n".join(from_lines), "\n".join(line for line in to_lines if normalize_text(line))


def _scr_or_placement(
    existing_from: Any,
    existing_to: Any,
    block_or_numbers: list[int],
    selected_block: dict[str, Any],
) -> tuple[str, str]:
    new_text = _or_range_text(block_or_numbers[0], block_or_numbers[-1] if len(block_or_numbers) > 1 else "")
    if selected_block.get("placement_override") == "NORMAL_APPEND" and not normalize_text(existing_from):
        return "NORMAL_APPEND", "New OR directly continues the previous collection day's OR/range."
    previous_day_text = normalize_text(selected_block.get("previous_or_text", ""))
    if not normalize_text(existing_from) and previous_day_text and is_continueable_or(previous_day_text, new_text):
        # Other Day Rule: a blank target row may still be the correct block
        # when the new OR directly follows yesterday's/prior day's OR.
        return "NORMAL_APPEND", "New OR directly continues the previous collection day's OR/range."
    if (
        not normalize_text(existing_from)
        and previous_day_text
        and selected_block.get("previous_or_closed")
        and not is_continueable_or(previous_day_text, new_text)
    ):
        # Other Day Rule: when yesterday's OR group is closed and today's new
        # OR is a different sequence, keep it under that closed block to
        # preserve the remaining SCR spaces, but keep it visually separate.
        return "BREAKLINE_APPEND", "Prior collection day's closed OR is not continueable; placing under it separately."
    if not normalize_text(existing_from):
        return "NEW_SPACE", "SCR VS BR block has available empty space."
    previous_text = _last_scr_or_group(existing_from, existing_to)
    if is_continueable_or(previous_text, new_text):
        # Same Day Rule and Other Day Rule: continueable ORs use normal append
        # so a range like 1001-1050 followed by 1051-1100 becomes 1001-1100.
        return "NORMAL_APPEND", "New OR directly follows the previous OR/range."
    if is_or_closed(selected_block):
        # Breakline placement: a non-continueable finished OR group remains
        # visually separate instead of being merged into a continuous OR range.
        return "BREAKLINE_APPEND", "Closed SCR VS BR OR group is not continueable; appending with a line break."
    return "BREAKLINE_APPEND", "Non-continueable OR is separated with a line break."


def _empty_block_respects_previous_or(score: dict[str, Any], new_or_text: str) -> bool:
    previous_text = normalize_text(score.get("previous_or_text", ""))
    # Other Day Rule: an empty current-day SCR block is available only when
    # it has no prior OR in that same block, or the new OR continues that prior OR.
    return not previous_text or is_continueable_or(previous_text, new_or_text)


def _empty_block_can_preserve_closed_previous_or(score: dict[str, Any], new_or_text: str) -> bool:
    previous_text = normalize_text(score.get("previous_or_text", ""))
    previous = parse_or_range(previous_text)
    new = parse_or_range(new_or_text)
    return bool(
        score.get("empty")
        and score.get("previous_or_closed")
        and previous["valid"]
        and new["valid"]
        and int(new["start"]) > int(previous["end"])
        and not is_continueable_or(previous_text, new_or_text)
    )


def _current_batch_continues_previous_block(score: dict[str, Any], current_ors: set[int]) -> bool:
    previous = parse_or_range(score.get("previous_or_text", ""))
    return bool(previous["valid"] and int(previous["end"]) + 1 in current_ors)


def _receipt_series_block_start(series: int) -> int:
    return ((series - 1) // RECEIPT_BLOCK_SIZE) * RECEIPT_BLOCK_SIZE + 1


def _receipt_series_block_end(series: int) -> int:
    return _receipt_series_block_start(series) + RECEIPT_BLOCK_SIZE - 1


def _remove_covered_or_amounts(or_amounts: list[Decimal], or_numbers: list[int], existing_from: Any, existing_to: Any) -> list[Decimal]:
    from_values = _parse_ors(existing_from)
    to_values = _parse_ors(existing_to)
    if len(from_values) != 1:
        return or_amounts
    start = from_values[0]
    end = to_values[0] if len(to_values) == 1 else start
    low, high = sorted((start, end))
    return [
        amount
        for amount, or_number in zip(or_amounts, or_numbers)
        if not (low <= int(or_number) <= high)
    ]


def _remove_covered_or_numbers(or_numbers: list[int], existing_from: Any, existing_to: Any) -> list[int]:
    from_values = _parse_ors(existing_from)
    to_values = _parse_ors(existing_to)
    if len(from_values) != 1:
        return or_numbers
    start = from_values[0]
    end = to_values[0] if len(to_values) == 1 else start
    low, high = sorted((start, end))
    return [
        or_number
        for or_number in or_numbers
        if not (low <= int(or_number) <= high)
    ]


def _range_from_ors(or_numbers: list[int], or_amounts: dict[int, Decimal]) -> dict[str, Any]:
    skipped: list[int] = []
    for previous_or, next_or in zip(or_numbers, or_numbers[1:]):
        if next_or - previous_or > 1:
            skipped.extend(range(previous_or + 1, next_or))
    amount = sum((or_amounts[number] for number in or_numbers), Decimal("0.00"))
    return {"FROM": or_numbers[0], "TO": or_numbers[-1], "AMOUNT": amount, "ORs": or_numbers, "Skipped ORs": skipped}


def _closed_block_key_for_or(or_number: int, row: list[Any]) -> int | None:
    for index, block in enumerate(RECEIPT_BLOCKS):
        if not _block_has_closed_range(row, block):
            continue
        from_values = _parse_ors(cell_value(row, block["from_col"] - 1))
        to_values = _parse_ors(cell_value(row, block["to_col"] - 1))
        start = from_values[0]
        end = to_values[0]
        low, high = sorted((start, end))
        if low <= int(or_number) <= high:
            return index
    return None


def split_ranges_by_existing_closed_blocks(or_ranges: list[dict[str, Any]], target_values: list[Any], or_amounts: dict[int, Decimal]) -> list[dict[str, Any]]:
    split_ranges: list[dict[str, Any]] = []
    for or_range in or_ranges:
        numbers = [int(number) for number in or_range.get("ORs", []) if int(number) in or_amounts]
        if len(numbers) <= 1:
            split_ranges.append(or_range)
            continue
        chunks: list[list[int]] = []
        current_chunk: list[int] = []
        current_key: int | None = None
        for number in numbers:
            key = _closed_block_key_for_or(number, target_values)
            if current_chunk and key != current_key:
                chunks.append(current_chunk)
                current_chunk = []
            current_chunk.append(number)
            current_key = key
        if current_chunk:
            chunks.append(current_chunk)
        if len(chunks) == 1:
            split_ranges.append(or_range)
            continue
        for chunk in chunks:
            split_range = _range_from_ors(chunk, or_amounts)
            if "Receipt Group" in or_range:
                split_range["Receipt Group"] = or_range["Receipt Group"]
            for key in ["Receipt Block Start", "Receipt Block End", "Receipt Block Closed"]:
                if key in or_range:
                    split_range[key] = or_range[key]
            split_range["OR Amounts"] = {number: or_amounts[number] for number in chunk}
            split_ranges.append(split_range)
    return split_ranges


def _assign_by_block_continuation(
    or_amounts: dict[int, Decimal],
    block_scores: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, Decimal]]:
    remaining = dict(sorted(or_amounts.items()))
    assigned: list[dict[str, Any]] = []
    initial_latest_by_index = {
        score["index"]: int(score["latest_or"])
        for score in block_scores
        if score["latest_or"] is not None
    }

    for score in sorted(
        [item for item in block_scores if item["latest_or"] is not None],
        key=lambda item: int(item["latest_or"]),
        reverse=True,
    ):
        latest_or = int(score["latest_or"])
        collected: list[int] = []
        while remaining:
            next_candidates = [number for number in remaining if number > latest_or]
            if not next_candidates:
                break
            next_or = min(next_candidates)
            if next_or - latest_or > SKIPPED_OR_GAP_LIMIT + 1:
                break
            other_continuation = any(
                other_index != score["index"] and other_latest == next_or - 1
                for other_index, other_latest in initial_latest_by_index.items()
            )
            if collected and other_continuation:
                break
            collected.append(next_or)
            latest_or = next_or
            del remaining[next_or]

        if collected:
            previous_or = int(score.get("previous_or", score["latest_or"]))
            score["latest_or"] = collected[-1]
            score["empty"] = False
            score["assigned_current_date"] = True
            assigned.append({
                **_range_from_ors(collected, or_amounts),
                **score["block"],
                "done": score.get("done", False),
                "initial_empty": score.get("initial_empty", False),
                "previous_or": previous_or,
                "previous_or_text": score.get("previous_or_text", ""),
                "previous_or_closed": score.get("previous_or_closed", False),
                "placement_override": "NORMAL_APPEND" if collected[0] == previous_or + 1 else "",
            })
    return assigned, remaining


def assign_scr_blocks(or_ranges: list[dict[str, Any]], sheet_rows: list[list[Any]], target_row: int, prefer_free_blocks: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_values = sheet_rows[target_row - 1] if target_row - 1 < len(sheet_rows) else []
    assigned: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    block_scores: list[dict[str, Any]] = []
    current_ors = {
        int(or_number)
        for or_range in or_ranges
        for or_number in or_range.get("ORs", [])
    }
    first_closed_index = next(
        (
            index
            for index, block in enumerate(RECEIPT_BLOCKS)
            if _block_has_closed_range(target_values, block)
        ),
        None,
    )

    for index, block in enumerate(RECEIPT_BLOCKS):
        before_latest = _latest_or_before_row(sheet_rows, target_row, block["from_col"], block["to_col"])
        previous_or_group = _previous_or_group_before_row(sheet_rows, target_row, block["from_col"], block["to_col"])
        previous_or_text = normalize_text(previous_or_group.get("text", ""))
        existing_from = normalize_text(cell_value(target_values, block["from_col"] - 1))
        existing_to = normalize_text(cell_value(target_values, block["to_col"] - 1))
        existing_ors = _block_existing_ors(target_values, block)
        existing_overlaps_current = bool(existing_ors & current_ors)
        has_closed_range = _block_has_closed_range(target_values, block)
        protect_closed_range = has_closed_range and (prefer_free_blocks or index == 0)
        closed_from_values = _parse_ors(existing_from)
        closed_to_values = _parse_ors(existing_to)
        closed_start = closed_from_values[0] if has_closed_range else None
        closed_end = closed_to_values[0] if has_closed_range else None
        block_empty = _block_is_empty(target_values, block) or (existing_overlaps_current and not protect_closed_range)
        block_scores.append(
            {
                "index": index,
                "block": block,
                "latest_or": before_latest,
                "previous_or_text": previous_or_text,
                "previous_or_closed": bool(previous_or_group.get("closed")),
                "empty": block_empty,
                "initial_empty": block_empty,
                "existing_ors": existing_ors,
                "closed_start": closed_start,
                "closed_end": closed_end,
                "protected_closed": protect_closed_range,
                "done": bool(
                    existing_from
                    and existing_to
                    and existing_from not in EMPTY_VALUES
                    and existing_to not in EMPTY_VALUES
                    and (protect_closed_range or not existing_overlaps_current)
                ),
            }
        )

    or_amounts: dict[int, Decimal] = {}
    for or_range in or_ranges:
        range_amounts = or_range.get("OR Amounts")
        if isinstance(range_amounts, dict):
            or_amounts.update(range_amounts)
        elif len(or_range["ORs"]) == 1:
            or_amounts[or_range["ORs"][0]] = or_range["AMOUNT"]

    if or_amounts and not any("Receipt Group" in or_range for or_range in or_ranges):
        continuation_assigned, remaining_amounts = _assign_by_block_continuation(or_amounts, block_scores)
        assigned.extend(continuation_assigned)
        or_ranges = contiguous_or_ranges(remaining_amounts)

    for or_range in or_ranges:
        start_or = int(or_range["FROM"])
        range_or_numbers = [int(number) for number in or_range.get("ORs", [])]
        new_or_text = _or_range_text(or_range["FROM"], or_range["TO"] if or_range["FROM"] != or_range["TO"] else "")
        covered_done_blocks = [
            score
            for score in block_scores
            if score.get("protected_closed")
            and _range_already_covered(
                cell_value(target_values, score["block"]["from_col"] - 1),
                cell_value(target_values, score["block"]["to_col"] - 1),
                range_or_numbers,
            )
        ]
        append_to_closed_blocks = [
            score
            for score in block_scores
            if (score.get("protected_closed") or score.get("current_receipt_closed"))
            and not score.get("current_receipt_continued")
            and score.get("closed_end") is not None
            and start_or > int(score["closed_end"])
        ]
        existing_match_blocks = [
            score
            for score in block_scores
            if not score.get("protected_closed")
            and start_or in score.get("existing_ors", set())
        ]
        candidates = [
            score
            for score in block_scores
            if (
                score["latest_or"] is not None
                and int(score["latest_or"]) < start_or
                and (
                    start_or - int(score["latest_or"]) <= SKIPPED_OR_GAP_LIMIT + 1
                    or (
                        score.get("assigned_current_date")
                        and not score.get("initial_empty")
                        and start_or == int(score["latest_or"]) + 1
                    )
                )
            )
        ]
        direct_continue_candidates = [
            score
            for score in candidates
            if score.get("latest_or") is not None
            and start_or == int(score["latest_or"]) + 1
        ]
        closed_previous_day_blocks = [
            score
            for score in block_scores
            if _empty_block_can_preserve_closed_previous_or(score, new_or_text)
            and not _current_batch_continues_previous_block(score, current_ors)
        ]
        continued_closed_receipt_block = False
        if covered_done_blocks:
            selected = covered_done_blocks[0]
        elif existing_match_blocks:
            selected = existing_match_blocks[0]
        elif direct_continue_candidates:
            # Continueable OR: continuation wins, even when the prior receipt
            # block was just closed on the same SCR date.
            selected = min(
                direct_continue_candidates,
                key=lambda score: (
                    not bool(score.get("assigned_current_date")),
                    int(score["index"]),
                ),
            )
            continued_closed_receipt_block = bool(
                selected.get("current_receipt_closed")
                and selected.get("closed_end") is not None
                and start_or == int(selected["closed_end"]) + 1
            )
        elif append_to_closed_blocks:
            selected = append_to_closed_blocks[0]
        elif closed_previous_day_blocks:
            selected = closed_previous_day_blocks[0]
        elif candidates:
            selected = min(candidates, key=lambda score: start_or - int(score["latest_or"]))
        else:
            done_blocks = [
                score
                for score in block_scores
                if score.get("done")
                and (
                    score.get("closed_end") is None
                    or start_or > int(score["closed_end"])
                )
            ]
            empty_blocks = [score for score in block_scores if score["empty"]]
            compatible_empty_blocks = [score for score in empty_blocks if _empty_block_respects_previous_or(score, new_or_text)]
            has_current_date_assignment = any(score.get("assigned_current_date") for score in block_scores)
            continued_done_blocks = [score for score in done_blocks if score.get("assigned_current_date")]
            if continued_done_blocks and compatible_empty_blocks:
                selected = compatible_empty_blocks[0]
            elif compatible_empty_blocks:
                if has_current_date_assignment:
                    latest_assigned_index = max(
                        int(score["index"])
                        for score in block_scores
                        if score.get("assigned_current_date")
                    )
                    selected = next(
                        (score for score in compatible_empty_blocks if int(score["index"]) > latest_assigned_index),
                        compatible_empty_blocks[0],
                    )
                else:
                    selected = compatible_empty_blocks[0]
            elif done_blocks:
                selected = done_blocks[0]
            else:
                occupied_blocks = [score for score in block_scores if not score["empty"]]
                if occupied_blocks:
                    # Conserve SCR space: a far-gap new range joins the first
                    # completed block before using empty blocks.
                    selected = next(
                        (score for score in occupied_blocks if score.get("done")),
                        occupied_blocks[0],
                    )
                else:
                    if not empty_blocks:
                        unassigned.append(or_range)
                        continue
                    selected = empty_blocks[0]
        selected["latest_or"] = int(or_range["TO"])
        selected["empty"] = False
        selected["assigned_current_date"] = True
        if continued_closed_receipt_block:
            selected["current_receipt_continued"] = True
        if or_range.get("Receipt Block Closed"):
            selected["done"] = True
            selected["current_receipt_closed"] = True
            selected["current_receipt_continued"] = False
            selected["closed_start"] = int(or_range["FROM"])
            selected["closed_end"] = int(or_range["TO"])
        assigned.append({
            **or_range,
            **selected["block"],
            "done": selected.get("done", False),
            "initial_empty": selected.get("initial_empty", False),
            "previous_or_text": selected.get("previous_or_text", ""),
            "previous_or_closed": selected.get("previous_or_closed", False),
        })
    return assigned, unassigned


def receipt_block_groups(receipt_preview: pd.DataFrame | None) -> dict[int, str]:
    if receipt_preview is None or receipt_preview.empty or "Series" not in receipt_preview:
        return {}
    groups: dict[int, str] = {}
    for row in receipt_preview.to_dict("records"):
        series = normalize_text(row.get("Series", ""))
        if not series.isdigit():
            continue
        type_col = normalize_text(row.get("Type Col", ""))
        series_col = normalize_text(row.get("Series Col", ""))
        date_col = normalize_text(row.get("Date Col", ""))
        amount_col = normalize_text(row.get("Amount Col", ""))
        if type_col or series_col or date_col or amount_col:
            block_start = _receipt_series_block_start(int(series))
            groups[int(series)] = f"{block_start}:{type_col}:{series_col}:{date_col}:{amount_col}"
    return groups


def receipt_grouped_or_ranges(or_amounts: dict[int, Decimal], receipt_groups: dict[int, str]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    used: set[int] = set()
    group_order: list[str] = []
    ors_by_group: dict[str, list[int]] = {}
    for or_number in sorted(or_amounts):
        group_key = receipt_groups.get(or_number)
        if not group_key:
            continue
        if group_key not in ors_by_group:
            group_order.append(group_key)
            ors_by_group[group_key] = []
        ors_by_group[group_key].append(or_number)
        used.add(or_number)

    for group_key in group_order:
        numbers = sorted(ors_by_group[group_key])
        if not numbers:
            continue
        grouped.append(
            {
                "FROM": numbers[0],
                "TO": numbers[-1],
                "AMOUNT": sum((or_amounts[number] for number in numbers), Decimal("0.00")),
                "ORs": numbers,
                "Receipt Group": group_key,
                "Receipt Block Start": _receipt_series_block_start(numbers[0]),
                "Receipt Block End": _receipt_series_block_end(numbers[0]),
                "Receipt Block Closed": numbers[-1] >= _receipt_series_block_end(numbers[0]),
                "Skipped ORs": [
                    missing
                    for previous, current in zip(numbers, numbers[1:])
                    for missing in range(previous + 1, current)
                ],
                "OR Amounts": {number: or_amounts[number] for number in numbers},
            }
        )

    grouped.extend(contiguous_or_ranges({number: amount for number, amount in sorted(or_amounts.items()) if number not in used}))
    return grouped


def fold_new_receipt_blocks_under_closed_scr_block(assigned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(assigned) < 2:
        return assigned
    anchor: dict[str, Any] | None = None
    for block in assigned:
        from_or = int(block["FROM"])
        to_or = int(block["TO"])
        if to_or > from_or:
            anchor = block
            break
    if anchor is None:
        return assigned

    anchor_end = int(anchor["TO"])
    anchor_cols = {
        "Block": anchor["Block"],
        "from_col": anchor["from_col"],
        "to_col": anchor["to_col"],
        "amount_col": anchor["amount_col"],
    }
    folded: list[dict[str, Any]] = []
    for block in assigned:
        if block is anchor:
            folded.append(block)
            continue
        block_ors = [int(or_number) for or_number in block.get("ORs", [])]
        if (
            len(block_ors) == 1
            and block_ors[0] > anchor_end
            and block.get("Receipt Group")
            and block.get("Receipt Group") == anchor.get("Receipt Group")
            and is_continueable_or(_or_range_text(anchor["FROM"], anchor["TO"]), str(block_ors[0]))
            and not block.get("initial_empty")
        ):
            folded.append({**block, **anchor_cols})
            continue
        folded.append(block)
    return folded


def prepare_scr_vs_br_updates(parsed_df: pd.DataFrame, sheet_rows: list[list[Any]], receipt_preview: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    errors: list[str] = []
    passed = parsed_df[parsed_df["Status"] == "PASSED"] if "Status" in parsed_df else pd.DataFrame()
    if passed.empty:
        return pd.DataFrame(), updates, errors

    date_rows = find_scr_date_rows(sheet_rows)
    receipt_groups = receipt_block_groups(receipt_preview)
    for scr_date, group in passed.groupby("Date"):
        iso_date = normalize_text(scr_date)
        target_row = date_rows.get(iso_date)
        total_collection = sum((parse_amount(value) for value in group["Actual Collection"]), Decimal("0.00"))
        or_amounts = {
            int(row["OR Number"]): parse_amount(row["Actual Collection"])
            for row in group.to_dict("records")
            if normalize_text(row.get("OR Number")).isdigit()
        }
        if target_row is None:
            errors.append(f"SCR VS BR date not found: {iso_date}")
            for or_range in contiguous_or_ranges(or_amounts):
                records.append(
                    {
                        "Target Tab": SCR_TAB,
                        "SCR DATE": iso_date,
                        "Target Row": "",
                        **or_range,
                        "Status": "ERROR",
                        "Issue": "SCR date not found",
                    }
                )
            continue

        target_values = sheet_rows[target_row - 1] if target_row - 1 < len(sheet_rows) else []
        or_ranges = receipt_grouped_or_ranges(or_amounts, receipt_groups) if receipt_groups else [
            {"FROM": number, "TO": number, "AMOUNT": amount, "ORs": [number], "Skipped ORs": [], "OR Amounts": {number: amount}}
            for number, amount in sorted(or_amounts.items())
        ]
        or_ranges = split_ranges_by_existing_closed_blocks(or_ranges, target_values, or_amounts)
        assigned, unassigned = assign_scr_blocks(or_ranges, sheet_rows, target_row, prefer_free_blocks=bool(receipt_groups))
        current_ors = set(or_amounts)

        working_cells: dict[int, Any] = {}
        cleared_cols: set[int] = set()
        updated_cols: set[int] = set()
        for index, block in enumerate(RECEIPT_BLOCKS):
            for col in [block["from_col"], block["to_col"], block["amount_col"]]:
                working_cells[col] = cell_value(target_values, col - 1)
            protect_closed_range = _block_has_closed_range(target_values, block) and (bool(receipt_groups) or index == 0)
            if (_block_existing_ors(target_values, block) & current_ors) and not protect_closed_range:
                for col in [block["from_col"], block["to_col"], block["amount_col"]]:
                    working_cells[col] = ""
                    cleared_cols.add(col)

        for block in assigned:
            to_value = block["TO"] if block["FROM"] != block["TO"] else ""
            existing_from = working_cells[block["from_col"]]
            existing_to = working_cells[block["to_col"]]
            block_or_numbers = [or_no for or_no in block["ORs"] if or_no in or_amounts]
            if _range_is_inner_duplicate(existing_from, existing_to, block_or_numbers):
                issue = f"Duplicate SCR VS BR OR posting blocked: {_or_range_text(block_or_numbers[0], block_or_numbers[-1] if len(block_or_numbers) > 1 else '')}"
                errors.append(issue)
                records.append(
                    {
                        "Target Tab": SCR_TAB,
                        "SCR DATE": iso_date,
                        "SCR AMOUNT": total_collection,
                        "Target Row": target_row,
                        "Block": block["Block"],
                        "FROM": block["FROM"],
                        "TO": to_value,
                        "AMOUNT": block["AMOUNT"],
                        "ORs": ", ".join(str(number) for number in block_or_numbers),
                        "Skipped ORs": ", ".join(str(number) for number in block.get("Skipped ORs", [])),
                        "Status": "ERROR",
                        "Issue": issue,
                        "SCRVSBR OR Placement": "BLOCK_POSTING_DUPLICATE_OR",
                        "SCRVSBR OR Placement Reason": "New OR overlaps an existing OR/range in the SCR VS BR target.",
                    }
                )
                continue
            block_or_numbers = _remove_covered_or_numbers(block_or_numbers, existing_from, existing_to)
            block_or_amounts = [or_amounts[or_no] for or_no in block_or_numbers]
            if not block_or_numbers or not block_or_amounts:
                continue
            write_from = block_or_numbers[0]
            write_to = block_or_numbers[-1] if len(block_or_numbers) > 1 else ""
            placement_type, placement_reason = _scr_or_placement(existing_from, existing_to, block_or_numbers, block)
            new_range_text = _or_range_text(write_from, write_to)
            if placement_type == "NORMAL_APPEND":
                previous_text = _last_scr_or_group(existing_from, existing_to)
                merged_text = append_or_normally(previous_text, new_range_text)
                working_cells[block["from_col"]], working_cells[block["to_col"]] = _replace_last_scr_or_group(
                    working_cells[block["from_col"]],
                    working_cells[block["to_col"]],
                    merged_text,
                )
            else:
                working_cells[block["from_col"]] = _append_scr_line(working_cells[block["from_col"]], write_from)
                working_cells[block["to_col"]] = _append_scr_line(working_cells[block["to_col"]], write_to)
            working_cells[block["amount_col"]] = _block_amount_value(
                working_cells[block["amount_col"]],
                block_or_amounts
            )
            updated_cols.update([block["from_col"], block["to_col"], block["amount_col"]])
            records.append(
                {
                    "Target Tab": SCR_TAB,
                    "SCR DATE": iso_date,
                    "SCR AMOUNT": total_collection,
                    "Target Row": target_row,
                    "Block": block["Block"],
                    "FROM": write_from,
                    "TO": write_to,
                    "AMOUNT": sum(block_or_amounts, Decimal("0.00")),
                    "ORs": ", ".join(str(number) for number in block_or_numbers),
                    "Skipped ORs": ", ".join(str(number) for number in block.get("Skipped ORs", [])),
                    "Status": "PASSED",
                    "Issue": "",
                    "SCRVSBR OR Placement": placement_type,
                    "SCRVSBR OR Placement Reason": placement_reason,
                    "Audit Action": "SCRVSBR_OR_PLACEMENT",
                    "previous_or": _last_scr_or_group(existing_from, existing_to)
                    or normalize_text(block.get("previous_or_text", ""))
                    or normalize_text(block.get("previous_or", "")),
                    "new_or": new_range_text,
                    "placement_type": placement_type,
                    "reason": placement_reason,
                    "collection_date": iso_date,
                }
            )

        if updated_cols or cleared_cols:
            working_cells[SCR_AMOUNT_COL] = decimal_to_display(total_collection)
            updated_cols.add(SCR_AMOUNT_COL)

        touched_cols = sorted(updated_cols | cleared_cols)
        updates.extend({"row": target_row, "col": col, "value": working_cells[col]} for col in touched_cols)

        for block in unassigned:
            records.append(
                {
                    "Target Tab": SCR_TAB,
                    "SCR DATE": iso_date,
                    "SCR AMOUNT": total_collection,
                    "Target Row": target_row,
                    "Block": "",
                    "FROM": block["FROM"],
                    "TO": block["TO"] if block["FROM"] != block["TO"] else "",
                    "AMOUNT": block["AMOUNT"],
                    "ORs": ", ".join(str(number) for number in block["ORs"]),
                    "Skipped ORs": ", ".join(str(number) for number in block.get("Skipped ORs", [])),
                    "Status": "ERROR",
                    "Issue": "No empty SCR VS BR receipt block",
                }
            )
        if unassigned:
            errors.append(f"SCR VS BR has no empty receipt block on {iso_date}")
    return pd.DataFrame(records), updates, errors
