"""draft: the request becomes a validated brief (§4). The topic stays exactly as entered (T01);
in production mode the LLM writes the learning outcome when the request did not give one.
"""

import json

from app.adapters import llm
from app.core import costs
from app.core.contracts import Brief
from app.nodes.context import Outputs, StageContext


def draft(ctx: StageContext) -> Outputs:
    request = json.loads(ctx.storage.read(f"{ctx.project_id}/request.json"))
    brief = Brief.model_validate(request["brief"])
    if brief.learning_outcome == request["prompt"]:  # defaulted to the prompt at creation
        writer = llm.get()
        brief = brief.model_copy(update={"learning_outcome": writer.learning_outcome(brief)})
        costs.record_usage(ctx.project_id, "draft", writer.calls)
    return {"brief.json": brief.model_dump_json(indent=2)}

