#!/usr/bin/env python3
"""Forward a GitHub issue-form submission into the Airtable Intake table.

Intake and Registry are separate tables on purpose: a submission is a claim,
a registry record is a verified claim. Nothing this script writes can reach
the published data without a maintainer moving it across.

Re-running for the same issue updates the existing record rather than
creating a second one, so an edited issue stays one row.

Usage:  python3 scripts/intake_to_airtable.py
Env:    AIRTABLE_TOKEN, AIRTABLE_BASE_ID,
        ISSUE_NUMBER, ISSUE_TITLE, ISSUE_BODY, ISSUE_URL
Requires: pip install requests
"""

import os
import re
import sys

import requests

from airtable_fields import INTAKE_TABLE

API = "https://api.airtable.com/v0"

# GitHub renders issue forms as `### Label` followed by the response.
SECTION_PATTERN = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
NO_RESPONSE = "_No response_"


def parse_issue_form(body: str) -> dict[str, str]:
    """Split a rendered issue-form body into {label: response}."""
    sections: dict[str, str] = {}
    matches = list(SECTION_PATTERN.finditer(body or ""))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        response = body[start:end].strip()
        if response and response != NO_RESPONSE:
            sections[match.group(1).strip()] = response
    return sections


def to_enum_token(label: str) -> str:
    """Normalize a form label to the schema's spelling.

    "External representation — agents speak for the org" -> "external-representation".
    Reviewers copy these straight into the Registry table's select fields, so
    emitting the schema token rather than the prose label saves a translation
    step and the transcription errors that come with it.
    """
    return label.split("—")[0].strip().lower().replace(" ", "-")


def checked_options(response: str) -> list[str]:
    """Pull the ticked boxes out of a checkbox section.

    Renders as `- [X] Governance — agents vote, propose, or decide policy`.
    """
    options = []
    for line in response.splitlines():
        if match := re.match(r"^\s*-\s*\[[xX]\]\s*(.+?)\s*$", line):
            options.append(to_enum_token(match.group(1)))
    return options


def airtable(method: str, path: str, token: str, **kwargs) -> dict:
    response = requests.request(
        method,
        f"{API}/{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    issue_number = os.environ.get("ISSUE_NUMBER")
    if not all([token, base_id, issue_number]):
        print(
            "AIRTABLE_TOKEN, AIRTABLE_BASE_ID and ISSUE_NUMBER must be set.",
            file=sys.stderr,
        )
        return 2

    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")
    url = os.environ.get("ISSUE_URL", "")
    sections = parse_issue_form(body)

    is_correction = title.startswith("[Correction]") or "Record" in sections

    fields = {
        "Submission": title or f"Issue #{issue_number}",
        "Issue Number": int(issue_number),
        "Issue URL": url,
        "Type": "Correction" if is_correction else "New AO",
        "Status": "New",
        "Raw Body": body,
    }

    # Lift the fields a reviewer sorts by out of the raw body. Everything
    # else stays in Raw Body rather than being guessed into typed columns.
    if name := sections.get("Organization name"):
        fields["Organization Name"] = name
    if website := sections.get("Website"):
        fields["Website"] = website
    if summary := sections.get("What does it do?"):
        fields["Summary"] = summary
    if oversight := sections.get("What keeps humans in control?"):
        fields["Human Oversight"] = oversight
    if sources := sections.get("Sources"):
        fields["Sources Given"] = sources
    if record := sections.get("Record"):
        fields["Target Record ID"] = record
    if roles := sections.get("Which functions do AI agents hold?"):
        fields["Agent Roles Claimed"] = ", ".join(checked_options(roles))
    if autonomy := sections.get("How much authority do agents actually exercise?"):
        # Store the schema-facing token, not the explanatory sentence.
        fields["Autonomy Claimed"] = to_enum_token(autonomy)
    if relationship := sections.get("Your relationship to this organization"):
        fields["Self Submission"] = relationship.lower().startswith("i work")

    existing = airtable(
        "GET",
        f"{base_id}/{INTAKE_TABLE}",
        token,
        params={
            "filterByFormula": f"{{Issue Number}} = {int(issue_number)}",
            "maxRecords": 1,
        },
    ).get("records", [])

    if existing:
        # Preserve Status — a reviewer may have moved it along since the
        # submitter last edited the issue.
        fields.pop("Status", None)
        airtable(
            "PATCH",
            f"{base_id}/{INTAKE_TABLE}",
            token,
            json={"records": [{"id": existing[0]["id"], "fields": fields}]},
        )
        print(f"Updated intake record for issue #{issue_number}.")
    else:
        airtable(
            "POST",
            f"{base_id}/{INTAKE_TABLE}",
            token,
            json={"records": [{"fields": fields}]},
        )
        print(f"Created intake record for issue #{issue_number}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
