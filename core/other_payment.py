from __future__ import annotations

from decimal import Decimal
from typing import Any

from .parser import normalize_text

OTHER_PAYMENT_SECTION_LABEL = "OTHERS"


def is_other_payment_transaction(account_name: str) -> bool:
    return "OTHER PAYMENT" in normalize_text(account_name).upper()


def format_other_payment_amount(amount: Any) -> str:
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    return f"({value:,.2f})"


def build_other_payment_accounts_entry(or_number: str, branch_name: str, amount: Any) -> str:
    return f"{or_number} - OTHER PAYMENT /{normalize_text(branch_name)}        {format_other_payment_amount(amount)}"


def annotate_other_payment_rows(parsed_df: Any) -> Any:
    records: list[dict[str, Any]] = []
    for row in parsed_df.to_dict("records"):
        row_data = dict(row)
        row_data.setdefault("is_other_payment", False)
        row_data.setdefault("other_payment_accounts_entry", "")
        if not row_data.get("is_ibp") and is_other_payment_transaction(row_data.get("Account Name", "")):
            row_data["is_other_payment"] = True
            if row_data.get("Status") == "PASSED":
                row_data["other_payment_accounts_entry"] = build_other_payment_accounts_entry(
                    row_data.get("OR Number", ""),
                    row_data.get("Account Name Only", ""),
                    row_data.get("Actual Collection", row_data.get("Amount", "0")),
                )
        records.append(row_data)
    return parsed_df.__class__(records)
