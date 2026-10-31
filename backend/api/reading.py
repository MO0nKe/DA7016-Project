"""Reading aids and app status: the supported languages, health and API usage, defining an English word (offline
WordNet)."""

from fastapi import APIRouter, HTTPException

from ..core.languages import LANGUAGES, RTL
from ..services.dictionary import DictionaryUnavailable, define
from .deps import ServicesDep

router = APIRouter(prefix="/api", tags=["reading"])


@router.get("/health")
def health(svc: ServicesDep):
    """Which APIs the backend talks to, and whether calls spend credits (the studio shows Live or Mock)."""
    s = svc.settings
    return {
        "status": "ok",
        "bodhan": s.bodhan_base_url,
        "openrouter": s.openrouter_base_url,
        "spends_credits": s.spends_credits,
    }


@router.get("/usage")
def usage(svc: ServicesDep):
    """API usage per host and model, from the ledger."""
    return svc.bodhan.ledger.summary()


@router.get("/languages")
def languages():
    """The supported languages: code, name and whether the script runs right to left."""
    return [{"code": c, "name": n, "rtl": c in RTL} for c, n in LANGUAGES.items()]


@router.get("/define")
def dictionary(word: str):
    """English definitions from the offline WordNet dictionary (no API calls)."""
    try:
        result = define(word)
    except DictionaryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if result is None:
        raise HTTPException(400, "select a single English word or short phrase")
    return result
