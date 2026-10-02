"""Safe persistence for agent events."""

import json
from pathlib import Path
from typing import Any

from controls import for_storage

#record->dump->for_storage()->COMPREHEND PII-> mask text-> file.write()
def write_record(
    record: dict[str, Any],
    path: str | Path = "agent.log",
    *,
    comprehend_client=None,
) -> None:
    """Persist a record only after applying the storage control."""

    raw_text = json.dumps(record)#transform record dictionaries into string represenation

    # Transform before writing. If the control fails, the exception
    # prevents raw personal data from being persisted.
    safe_text = for_storage(
        raw_text,
        comprehend_client=comprehend_client,
    )

    #want to make sure PII is masked BEFORE writing to file 
    with Path(path).open("a", encoding="utf-8") as file:
        file.write(safe_text + "\n")