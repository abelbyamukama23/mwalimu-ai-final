"""Contract #1-#6 validation runner (self-contained; real DeepSeek).

Run inside the Platform API project (uv run, PYTHONPATH=src, DJANGO_SETTINGS_MODULE set)
after migrations and while the platform (8000) + agent (8001) services are up.

Seeds a test user, regional context, and one indexed personal-library document, then
exercises: teaching loop (2 turns), regional grounding, personal-library retrieval +
citation integrity, and a direct non-learning request. Exits non-zero on failure.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "platform_api.settings")
django.setup()

import httpx  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402

from platform_api.apps.context.models import (  # noqa: E402
    ContextDomain,
    ContextResource,
    ContextResourceStatus,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    GeographicUnitType,
    UserFamiliarRegion,
)
from platform_api.apps.libraries.models import Library, LibraryStatus  # noqa: E402
from platform_api.apps.processing.chunker import chunk  # noqa: E402
from platform_api.apps.processing.embedding import get_embedding_provider  # noqa: E402
from platform_api.apps.processing.extractors import extract  # noqa: E402
from platform_api.apps.processing.indexing import (  # noqa: E402
    activate_run,
    write_chunks_and_embeddings,
)
from platform_api.apps.processing.models import ProcessingRun, ProcessingStatus  # noqa: E402
from platform_api.apps.processing.normalizer import normalize  # noqa: E402
from platform_api.apps.processing.tasks import _get_extractor_version  # noqa: E402
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType  # noqa: E402
from platform_api.apps.resources.object_key import generate_resource_object_key  # noqa: E402
from platform_api.apps.users.models import UserPreference  # noqa: E402

USER = get_user_model()
API = "http://localhost:8000"
EMAIL = f"contract-{uuid.uuid4().hex[:12]}@example.test"
PASSWORD = "Contract!234"
PROMPT_OSMOSIS = "Explain osmosis to me step by step, then ask one short question."
PROMPT_CHAMELEON = "What does the Mwalimu Chameleon feed on, and when does its skin glow? Check my library."
PROMPT_REGIONAL = "Explain how bimodal rainfall affects crop farming in my area."

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def seed() -> None:
    user = USER.objects.create_user(email=EMAIL, password=PASSWORD)
    UserPreference.objects.get_or_create(user=user, defaults=dict(
        pedagogical_style="intuitive", explanation_depth="standard", response_language="en",
    ))

    salt = uuid.uuid4().hex[:8]
    unit, _ = GeographicUnit.objects.get_or_create(
        slug=f"tororo-{salt}",
        defaults=dict(
            name="Tororo", unit_type=GeographicUnitType.DISTRICT,
            status=GeographicUnitStatus.ACTIVE, country_code="UG",
        ),
    )
    domain, _ = ContextDomain.objects.get_or_create(
        name=f"Agriculture-{salt}", slug=f"agriculture-{salt}"
    )
    ContextResource.objects.get_or_create(
        geographic_unit=unit,
        context_domain=domain,
        title="Tororo Farming",
        defaults=dict(
            content=(
                "In Tororo district the main food crops are cassava and maize. Rainfall "
                "is bimodal: long rains March to May, short rains September to November."
            ),
            scope_type=ContextScopeType.PLATFORM,
            status=ContextResourceStatus.ACTIVE,
            applicable_subjects=["agriculture"],
            applicable_topics=["crops", "rainfall", "farming"],
            pedagogical_purposes=["example", "explanation"],
        ),
    )
    UserFamiliarRegion.objects.get_or_create(user=user, geographic_unit=unit, defaults=dict(priority=1))

    library, _ = Library.objects.get_or_create(
        owner=user, slug=f"field-notes-{salt}",
        defaults=dict(name="Field Notes", status=LibraryStatus.ACTIVE),
    )
    text = (
        "Field note: The Mwalimu Chameleon lives in the Kifumbira wetlands. It feeds "
        "only on the purple-lip fog beetle. Its skin glows teal at night during the "
        "short rains. Researchers first observed it in 2019 near Lake Victoria."
    )
    body = text.encode("utf-8")
    resource, created = Resource.objects.update_or_create(
        library=library,
        name=f"Kifumbira Notes {salt}",
        defaults=dict(
            resource_type=ResourceType.TXT,
            original_filename="kifumbira.txt",
            content_type="text/plain",
            size=len(body),
            object_key=generate_resource_object_key(library.pk, uuid.uuid4()),
            checksum=hashlib.sha256(body).hexdigest(),
            status=ResourceStatus.READY,
            created_by=user,
        ),
    )
    if created or not ProcessingRun.objects.filter(resource=resource).exists():
        provider = get_embedding_provider()
        run = ProcessingRun.objects.create(
            resource=resource,
            library=library,
            status=ProcessingStatus.PROCESSING,
            source_checksum=resource.checksum,
            pipeline_version="1",
            extractor_version=_get_extractor_version(ResourceType.TXT),
            chunker_version="1",
            embedding_model=provider.model_id,
            embedding_version=provider.embedding_version,
            embedding_dimensions=provider.dimensions,
            is_active=False,
        )
        extracted = extract(body, ResourceType.TXT)
        normalized = normalize(extracted)
        chunks = chunk(normalized)
        vectors = provider.embed_texts([c.text for c in chunks])
        write_chunks_and_embeddings(run, chunks, vectors)
        activate_run(run)
    return user, unit


def login_token() -> str:
    r = httpx.post(f"{API}/api/v1/auth/login/", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["access"]


def new_session(token: str, title: str) -> str:
    r = httpx.post(f"{API}/api/v1/sessions/", headers={"Authorization": f"Bearer {token}"}, json={"title": title}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def run_prompt(token: str, session_id: str, prompt: str, scope: str = "public") -> dict:
    h = {"Authorization": f"Bearer {token}"}
    r = httpx.post(
        f"{API}/api/v1/sessions/{session_id}/runs/",
        headers=h,
        json={"prompt": prompt, "tool_allowlist": ["knowledge_search"], "knowledge_scope": scope},
        timeout=30,
    )
    r.raise_for_status()
    run_id = r.json()["id"]
    for _ in range(120):
        snap = httpx.get(f"{API}/api/v1/runs/{run_id}/", headers=h, timeout=30).json()
        if snap["status"] in ("completed", "failed", "cancelled", "timed_out"):
            return snap
        time.sleep(1)
    return {"status": "TIMEOUT", "answer": None, "citations": []}


def main() -> int:
    user, unit = seed()
    token = login_token()

    # Contract #3 + #4: teaching loop + adaptation (2 turns)
    sid = new_session(token, "teaching")
    t1 = run_prompt(token, sid, PROMPT_OSMOSIS, "public")
    answer1 = t1.get("answer") or ""
    check("teaching_turn1_has_comprehension_question", "?" in answer1 and len(answer1) > 40)
    t2 = run_prompt(token, sid, "The beans become bigger.", "public")
    answer2 = t2.get("answer") or ""
    check("teaching_turn2_reacts", answer2 != answer1 and len(answer2) > 20)

    # Contract #2: personal-library retrieval + citation integrity
    sid2 = new_session(token, "grounding")
    g = run_prompt(token, sid2, PROMPT_CHAMELEON, "my")
    answer_g = g.get("answer") or ""
    check("grounding_retrieved_doc", "purple-lip" in answer_g, answer_g[:80])
    check("grounding_citation_present", len(g.get("citations", [])) > 0)

    sid3 = new_session(token, "grounding-public")
    gpub = run_prompt(token, sid3, PROMPT_CHAMELEON, "public")
    answer_pub = gpub.get("answer") or ""
    check("grounding_public_excludes_doc", "purple-lip" not in answer_pub)
    check("grounding_public_no_citation", len(gpub.get("citations", [])) == 0)

    # Contract #1: regional context influences the answer when relevant
    sid4 = new_session(token, "regional")
    reg = run_prompt(token, sid4, PROMPT_REGIONAL, "public")
    answer_reg = (reg.get("answer") or "").lower()
    check("regional_grounding_used", any(k in answer_reg for k in ["march", "may", "september", "november", "tororo", "cassava"]))

    # Non-learning request -> direct, no quiz
    sid5 = new_session(token, "direct")
    d = run_prompt(token, sid5, "What is the capital of France?", "public")
    answer_d = (d.get("answer") or "").lower()
    check("direct_answer", "paris" in answer_d and len(d.get("answer") or "") < 300)

    if FAILURES:
        print(f"\n{len(FAILURES)} contract checks FAILED: {FAILURES}")
        return 1
    print("\nAll contract checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
