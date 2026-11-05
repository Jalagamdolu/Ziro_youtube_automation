"""No login (D-61): the studio runs on one machine for its one reviewer, so every request acts as
Dolender, and every gate decision records that name in the approvals table."""

from typing import Any

from fastapi import Request
from fastapi.responses import Response

REVIEWER = {"name": "Dolender"}


async def middleware(request: Request, call_next: Any) -> Response:
    request.state.user = REVIEWER
    response: Response = await call_next(request)
    return response
