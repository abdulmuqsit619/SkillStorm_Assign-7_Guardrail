"""AgentCore warranty claim agent for the PII leak lab."""

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from opentelemetry.instrumentation.langchain import LangchainInstrumentor

from controls import for_partner
from model.load import load_model
from store import write_record
from tools import read_warranty_claim, send_to_repair_partner


LangchainInstrumentor().instrument()

app = BedrockAgentCoreApp()
log = app.logger

_llm = None


def get_or_create_model():
    """Load the Bedrock model once and reuse it."""
    global _llm

    if _llm is None:
        _llm = load_model()

    return _llm


DEFAULT_SYSTEM_PROMPT = """
You are a warranty claim support assistant.

Help customers understand the status of their warranty claims.

Use read_warranty_claim when you need information about a claim.

The warranty record may contain internal fields that are not intended for the
customer. Never reveal internal_notes or payment information to the customer.

If a repair partner needs to be contacted, only approved information may be
sent to that partner.

Do not invent warranty claim information.
"""


def prepare_partner_contact(
    record: dict[str, Any],
    *,
    guardrail_client=None,
) -> dict[str, Any]:
    """Apply the outbound control before calling the partner tool."""

    safe_payload = for_partner(
        record,
        guardrail_client=guardrail_client,
    )

    return send_to_repair_partner.invoke(safe_payload)


tools = [read_warranty_claim]


@app.entrypoint
async def invoke(payload, context):
    """Run the warranty support agent."""

    #does not contain Pii info to log
    log.info("Invoking warranty claim agent")

    prompt = payload.get(
        "prompt",
        "What can you help me with?",
    )

    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string")

    # Persist the request only through the storage control.
    # Never log the raw prompt directly.
    write_record(#HAS the PII info, but will be masked before writing to file
        {
            "event": "customer_request",
            "message": prompt,
        }
    )

    graph = create_react_agent(
        get_or_create_model(),
        tools=tools,
        prompt=DEFAULT_SYSTEM_PROMPT,
    )

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(content=prompt),
            ]
        }
    )

    output = result["messages"][-1].content

    # Persist the response through the same storage boundary.
    write_record(
        {
            "event": "agent_response",
            "message": output,
        }
    )

    log.info("Warranty claim request completed")

    return {"result": output}


if __name__ == "__main__":
    app.run()