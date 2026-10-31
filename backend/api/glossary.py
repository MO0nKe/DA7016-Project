"""The glossary: pinned term translations shared by all documents, and which sections don't use them."""

from fastapi import APIRouter, HTTPException

from ..pipeline.glossary import Term, misses
from .deps import ServicesDep, check_lang

router = APIRouter(prefix="/api", tags=["glossary"])


@router.get("/glossary", response_model=list[Term])
def list_terms(svc: ServicesDep):
    """Every glossary term, in all languages."""
    return svc.glossary.terms()


@router.post("/glossary", response_model=Term)
def add_term(term: Term, svc: ServicesDep):
    """Add a term that translation must keep, and return it with its id."""
    check_lang(term.lang)
    return svc.glossary.add(term)


@router.delete("/glossary/{term_id}")
def delete_term(term_id: str, svc: ServicesDep):
    """Delete one glossary term."""
    if not svc.glossary.remove(term_id):
        raise HTTPException(404, f"no term {term_id}")
    return {"deleted": term_id}


@router.get("/documents/{doc_id}/glossary-check")
def glossary_check(doc_id: str, lang: str, svc: ServicesDep):
    """Translated sections that don't use a pinned term's translation."""
    check_lang(lang)
    return misses(svc.document(doc_id), lang, svc.glossary.terms())
