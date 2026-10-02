"""Destination-specific controls for sensitive data.

Controls are named after the destination of the data rather than individual
PII types. This keeps the policy focused on what each destination is allowed
to receive.
"""

import json
import os
from typing import Any

import boto3


def for_partner(
    record: dict[str, Any],
    *,
    guardrail_client=None,
) -> dict[str, Any]:
    """Prepare the minimum information allowed to reach the repair partner."""

    # Use an allow-list rather than removing known sensitive fields.
    # In the case a new field is added to the internal record later
    # automatically become part of the outbound partner payload.
    allowed = {#This specifices what we want/ tool wants
        "claim_id": record["claim_id"],
        "callback_requested": bool(record.get("callback_requested", False)),
    }#only these two fields are allowed to be sent to the partner

    client = guardrail_client or boto3.client("bedrock-runtime")

    response = client.apply_guardrail(#decision api, ask if content is ALLOWED 
        guardrailIdentifier=os.environ["GUARDRAIL_ID"],
        guardrailVersion=os.environ.get("GUARDRAIL_VERSION", "DRAFT"),
        source="OUTPUT",
        content=[
            {
                "text": {
                    "text": json.dumps(allowed),
                }
            }
        ],
    )

    # Fail closed: if the guardrail decides this payload should not leave
    # the application, do not call the partner.
    if response.get("action") == "GUARDRAIL_INTERVENED":
        raise ValueError("Partner payload rejected by guardrail")

    return allowed

#REPS custom message -> for storage -> [find PII] -> [mask PII]-> LOG
def for_storage(
    text: str,
    *,
    comprehend_client=None,
) -> str:
    """Transform text into a representation safe for persistence."""

    if not text:
        return text

    client = comprehend_client or boto3.client("comprehend")

    response = client.detect_pii_entities(
        Text=text,
        LanguageCode="en",
    )

    entities = response.get("Entities", [])

    redacted = text

    # Replace entities from right to left. Replacing an earlier piece of text
    # first could change the offsets of entities appearing later in the text.
    for entity in sorted(
        entities,
        key=lambda item: item["BeginOffset"],
        reverse=True,
    ):
        start = entity["BeginOffset"]
        end = entity["EndOffset"]
        entity_type = entity["Type"]

        redacted = (
            redacted[:start]
            + f"[{entity_type}]"
            + redacted[end:]
        )

    return redacted