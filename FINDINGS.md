# Findings

This demonstrates three possible personal-data leak boundaries in an
AgentCore warranty claim assistant: data entering the agent, data leaving the
agent for a third party, and data persisted by the application.

| **Leak** | **Where the data crossed** | **Where I closed it** | **What it still misses** |
| -------- | -------------------------- | --------------------- | ------------------------ |
| OUT | Internal warranty claim data from the agent toward the simulated repair partner. `for_partner()` creates an allow-listed payload only having `claim_id` and `callback_requested`, then uses Bedrock `ApplyGuardrail` as a policy decision before sending payload. The allow-list must be reviewed if the partner's data requirements change. guardrail can also only detect content covered by its configured policies, so the allow-list remains the primary data-minimization control. |
| IN | Data crossed from the fake warranty store into the agent through `read_warranty_claim()`. The `internal_notes` field intentionally has a test card number that should not have been stored there.  Closing this leak would require inspecting or transforming tool results before they enter the model context. That would add cost and latency and could remove information that is  needed for reasoning. instead use a field-level allow-listing or PII transformation to tool results before exposing them to the model. |
| STORED | Customer messages and agent responses crossed from runtime data into the local audit log. | `write_record()` sends serialized records through `for_storage()` before opening and writing the log file. `for_storage()` uses Comprehend `DetectPiiEntities` and replaces detected spans with entity labels such as `[EMAIL]` and `[PHONE]`. | PII detection is not a guarantee. Unsupported formats, low-confidence detections, or sensitive business information that is not classified as PII could still be missed. Additional application-specific controls would be needed for those cases. |

## Fail open or fail closed?

The storage control fails closed. If Comprehend is unavailable or
`DetectPiiEntities` raises an exception, execution stops before the log file is
opened and written.  storing the raw record when the protection service is unavailable would recreate the STORED leak.

The outbound control also fails closed when Bedrock Guardrails reports
`GUARDRAIL_INTERVENED`. The partner call is not allowed to continue with a
payload that failed the outbound policy check.

## Why each API is used

I use `ApplyGuardrail` in `for_partner()` because the outbound boundary
needs a policy decision about whether content is valid to send. The
allow-list performs the primary data minimization, while the guardrail provides
an additional decision before data crosses the partner boundary.

I use Comprehend `DetectPiiEntities` in `for_storage()` this
requires a transformation rather than only a yes/no decision. Comprehend returns
PII entity types and character offsets, which allows detected personal data to
be replaced before the record is written.

## What I would do with another day

With another day, I would address the IN leak by adding a destination-specific
control between the backing-store tool and the model context. I would evaluate
which fields the model actually needs and allow-list those fields, while
transforming sensitive information inside unstructured fields such as
`internal_notes`.

I would also add tests for guardrail intervention, Comprehend service failures,
multiple PII values, malformed backing-store records, and newly introduced
fields. For a production system, I would replace the local log with managed
storage and add monitoring for blocked outbound requests and failed redaction
operations without recording the sensitive values themselves.