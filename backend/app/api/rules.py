"""Rules API — admin CRUD for the central signal rule set.

Endpoints
---------
GET    /rules              — list all rules
POST   /rules              — create a new rule; hot-reloads engine
PATCH  /rules/{id}         — partial update; hot-reloads engine
DELETE /rules/{id}         — delete rule; hot-reloads engine
GET    /rules/metrics      — metric catalog (for the Strategy Lab builder UI)
POST   /rules/preview      — evaluate a draft rule against current TickerStates

Every mutation calls engine.set_rules(store.as_rules()) to keep the live
signal stream up-to-date without a restart.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.rules import RuleEngine, catalog, compile_condition, validate_logic
from backend.app.rules.rule import Rule

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------

class RuleCreate(BaseModel):
    name: str
    logic: dict
    enabled: bool = True
    severity: str = "info"
    side_label: Optional[str] = None
    kind: str = "SIGNAL"
    cooldown_s: float = 300.0


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    logic: Optional[dict] = None
    enabled: Optional[bool] = None
    severity: Optional[str] = None
    side_label: Optional[str] = None
    kind: Optional[str] = None
    cooldown_s: Optional[float] = None


class PreviewRequest(BaseModel):
    logic: dict
    enabled: bool = True
    severity: str = "info"
    side_label: Optional[str] = None
    kind: str = "SIGNAL"
    cooldown_s: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hot_reload(request: Request) -> None:
    """Re-load rules from store into the live engine."""
    engine: RuleEngine = request.app.state.engine
    store = request.app.state.rules_store
    engine.set_rules(store.as_rules())


def _validate_logic(logic: dict) -> None:
    try:
        validate_logic(logic)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid rule logic: {exc}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/metrics")
def get_metrics():
    """Metric catalog for the Strategy Lab rule-builder UI."""
    return {"metrics": catalog()}


@router.get("")
def list_rules(request: Request):
    store = request.app.state.rules_store
    return {"rules": store.all_rules()}


@router.post("", status_code=201)
def create_rule(body: RuleCreate, request: Request):
    _validate_logic(body.logic)
    store = request.app.state.rules_store
    rule = Rule(
        name=body.name,
        logic=body.logic,
        enabled=body.enabled,
        severity=body.severity,
        side_label=body.side_label,
        kind=body.kind,
        cooldown_s=body.cooldown_s,
    )
    created = store.insert_rule(rule, is_builtin=False)
    _hot_reload(request)
    return {"rule": created}


@router.patch("/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdate, request: Request):
    store = request.app.state.rules_store
    if store.get_rule(rule_id) is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    if body.logic is not None:
        _validate_logic(body.logic)

    updates: Dict[str, Any] = body.model_dump(exclude_none=True)
    updated = store.update_rule(rule_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    _hot_reload(request)
    return {"rule": updated}


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, request: Request):
    store = request.app.state.rules_store
    if not store.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    _hot_reload(request)


@router.post("/preview")
def preview_rule(body: PreviewRequest, request: Request):
    """Evaluate a draft rule against current TickerStates and return matching symbols.

    Uses `engine.preview()` which probes each symbol's last known state
    with a synthetic event carrying the last price. No signal is emitted;
    no state is mutated.
    """
    _validate_logic(body.logic)
    engine: RuleEngine = request.app.state.engine

    draft = Rule(
        name="_preview",
        logic=body.logic,
        enabled=True,
        severity=body.severity,
        side_label=body.side_label,
        kind=body.kind,
        cooldown_s=0.0,
    )
    try:
        matches = engine.preview(draft)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Preview failed: {exc}")

    return {
        "matched": matches,
        "total": len(matches),
        "universe_size": len(engine.universe()),
    }
