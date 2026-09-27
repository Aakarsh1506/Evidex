from fastapi import APIRouter, Depends, Request

from ..errors import APIError, api_errors
from ..security import require_auth
from ..services.case_summary import generate_case_summary, store_summary
from ..services.cases import list_cases, load_case, load_summary, matches
from ..services.groq import explain_network
from ..services.insight import build_insight_context, validate_selection
from ..services.investigator_chat import validate_history
from ..services.network import fetch_case_network
from ..services.ollama import explain_insight
from ..services.rag import retrieve_context

router = APIRouter(prefix="/api/cases", tags=["Cases"], dependencies=[Depends(require_auth)])


@router.get("/", include_in_schema=False)
@router.get("")
async def get_cases(request: Request, q: str = "", tags: str = "", all: str = ""):
    with api_errors("Failed to load cases"):
        cases = await list_cases(request.app.state.db)
        query = q.lower().strip()
        wanted_tags = [tag.strip().lower() for tag in tags.split(",") if tag.strip()]
        if query or wanted_tags:
            return [case for case in cases if matches(case, query, wanted_tags)]
        # An empty search only lists every case when explicitly requested.
        return cases if all == "true" else []


@router.get("/{case_id}")
async def get_case(case_id: str, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to load case"):
        case = await load_case(case_id, request.app.state.db, officer["officerId"])
        if case is None:
            raise APIError("Not found", 404)
        return case


@router.get("/{case_id}/network")
async def get_case_network(case_id: str, request: Request):
    with api_errors("Failed to load case network"):
        network = await fetch_case_network(case_id, request.app.state.graph.run)
        if network is None:
            raise APIError("Network not found for this case", 404)
        return network


@router.post("/{case_id}/summary")
async def create_summary(case_id: str, request: Request, officer=Depends(require_auth)):
    try:
        body = await request.json()
    except ValueError:
        body = {}
    language = body.get("language", "en") if isinstance(body, dict) else "en"
    if language not in ("en", "hi"):
        raise APIError("Summary language must be en or hi.", 400)
    state = request.app.state
    if state.active_explanations >= 3:
        raise APIError("AI is busy. Please try again shortly.", 429)
    state.active_explanations += 1
    try:
        with api_errors("Unable to generate the case summary. Stored records remain available."):
            case = await load_case(case_id, state.db, officer["officerId"])
            if case is None:
                raise APIError("Case not found.", 404)
            summary = await generate_case_summary(
                case, state.db, state.http_client, state.settings, officer["officerId"], language
            )
            await store_summary(state.db, case_id, officer["officerId"], language, summary)
            # Read it back so the response carries the stored timestamp and author.
            return await load_summary(case_id, state.db)
    finally:
        state.active_explanations -= 1


@router.post("/{case_id}/explain")
async def explain(case_id: str, request: Request, officer=Depends(require_auth)):
    try:
        body = await request.json()
    except ValueError:
        raise APIError("Select a node or relationship to generate AI insight.", 400) from None
    selection = body.get("selection") if isinstance(body, dict) else None
    question = body.get("question", "") if isinstance(body, dict) else ""
    if not isinstance(question, str) or len(question) > 2000:
        raise APIError("Question must be 2,000 characters or fewer.", 400)
    history = validate_history(body.get("history", []) if isinstance(body, dict) else [])
    # A question may be asked about the whole network; an insight still needs a selected record.
    if selection is not None or not question.strip():
        validate_selection(selection)
    state = request.app.state
    use_ollama = state.settings.extraction_provider == "ollama"
    if not use_ollama and not state.settings.groq_api_key.strip():
        raise APIError(
            "AI is not configured. Add GROQ_API_KEY to backend/.env and restart the server.", 503
        )
    if state.active_explanations >= 3:
        raise APIError("AI is busy. Please try again shortly.", 429)
    state.active_explanations += 1
    try:
        with api_errors("Unable to load records for the AI insight. Please try again."):
            case = await load_case(case_id, state.db, officer["officerId"])
            if case is None:
                raise APIError("Case not found.", 404)
            network = await fetch_case_network(case_id, state.graph.run)
            context = build_insight_context(network, selection)
            if question.strip():
                context["investigator_question"] = question.strip()
                context["conversation_history"] = history
                context["retrieved_evidence"] = [
                    {
                        "documentId": row["document_id"],
                        "document": row["original_name"],
                        "sourceStart": row["source_start"],
                        "sourceEnd": row["source_end"],
                        "text": row["chunk_text"],
                    }
                    for row in await retrieve_context(
                        state.db, officer["officerId"], question, case_id=case_id,
                        settings=state.settings, client=state.http_client,
                    )
                ]
            if use_ollama:
                import json

                explanation = await explain_insight(
                    state.http_client, state.settings,
                    json.dumps(context, ensure_ascii=False, separators=(",", ":")),
                    thinking=bool(question.strip()),
                )
            else:
                # explain_network expects a named record; the case reference is its identity.
                explanation = await explain_network(
                    {"criminal": {"id": case["id"], "name": case["reference"],
                                  "location": case["location"], "crimeTags": case["crimeTags"],
                                  "cases": []}, "relations": []},
                    insight_context=context,
                    api_key=state.settings.groq_api_key,
                    model=state.settings.groq_model,
                    client=state.http_client,
                )
            return {"explanation": explanation}
    finally:
        state.active_explanations -= 1
