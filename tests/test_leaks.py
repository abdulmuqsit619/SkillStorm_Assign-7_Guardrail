"""Tests proving that OUT and STORED PII leaks are closed."""

import sys
from pathlib import Path

# Allow tests to import modules from app/LabAgent when pytest runs
# from the repository root.
AGENT_DIR = Path(__file__).resolve().parents[1] / "app" / "LabAgent"
sys.path.insert(0, str(AGENT_DIR))

from controls import for_partner
from store import write_record


TEST_EMAIL = "jordan.test@example.com"
TEST_PHONE = "555-010-2222"


class FakeGuardrailClient:
    """Fake Bedrock client so unit tests do not require AWS credentials."""

    def apply_guardrail(self, **kwargs):
        return {
            "action": "NONE",
            "outputs": [],
        }


class FakeComprehendClient:
    """Fake Comprehend client that identifies our fabricated PII."""

    def detect_pii_entities(self, *, Text, LanguageCode):
        entities = []

        test_values = [
            (TEST_EMAIL, "EMAIL"),
            (TEST_PHONE, "PHONE"),
        ]

        for value, entity_type in test_values:
            start = Text.find(value)

            if start != -1:
                entities.append(
                    {
                        "Type": entity_type,
                        "Score": 0.99,
                        "BeginOffset": start,
                        "EndOffset": start + len(value),
                    }
                )

        return {"Entities": entities}


def test_partner_payload_contains_no_raw_personal_data(monkeypatch):
    """The repair partner must not receive customer email or phone."""

    monkeypatch.setenv("GUARDRAIL_ID", "test-guardrail")
    monkeypatch.setenv("GUARDRAIL_VERSION", "DRAFT")

    record = {
        "claim_id": "WC-1001",
        "callback_requested": True,
        "customer_name": "Jordan Test",
        "email": TEST_EMAIL,
        "phone": TEST_PHONE,
        "internal_notes": (
            "Diagnostic fee recorded with test card "
            "4111 1111 1111 1111."
        ),
    }

    payload = for_partner(
        record,
        guardrail_client=FakeGuardrailClient(),
    )

    payload_text = str(payload)

    assert TEST_EMAIL not in payload_text
    assert TEST_PHONE not in payload_text
    assert "customer_name" not in payload
    assert "internal_notes" not in payload

    assert payload == {
        "claim_id": "WC-1001",
        "callback_requested": True,
    }


def test_persisted_record_contains_no_raw_personal_data(tmp_path):
    """Raw email and phone values must never reach persisted storage."""

    log_file = tmp_path / "agent.log"

    record = {
        "event": "customer_request",
        "message": (
            f"My email is {TEST_EMAIL} "
            f"and my phone is {TEST_PHONE}."
        ),
    }

    write_record(
        record,
        log_file,
        comprehend_client=FakeComprehendClient(),
    )

    stored = log_file.read_text(encoding="utf-8")

    assert TEST_EMAIL not in stored
    assert TEST_PHONE not in stored

    assert "[EMAIL]" in stored
    assert "[PHONE]" in stored