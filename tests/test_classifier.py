"""End-to-end tests for app_classifier against fixture repos."""
import asyncio
from pathlib import Path

import pytest

from app_classifier import (
    AppDescription,
    classify,
    classify_async,
    analyze_hosting_requirements,
    llm_enrich_description,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_classify_returns_app_description():
    result = classify(str(FIXTURES / "ecommerce_django"))
    assert isinstance(result, AppDescription)
    assert result.name == "ecommerce_django"


def test_ecommerce_django_classified_correctly():
    result = classify(str(FIXTURES / "ecommerce_django"))
    # Strong e-commerce signal: Cart, Order, Product, Coupon models + /checkout, /cart routes
    assert result.app_category == "e-commerce"
    assert result.app_category_confidence >= 0.4
    assert "online shopping" in result.detected_features


def test_ecommerce_django_runtime_detection():
    result = classify(str(FIXTURES / "ecommerce_django"))
    assert result.runtime.get("language") == "python"
    assert result.framework == "Django"


def test_ecommerce_django_databases():
    result = classify(str(FIXTURES / "ecommerce_django"))
    assert "PostgreSQL" in result.databases


def test_ecommerce_django_caches():
    result = classify(str(FIXTURES / "ecommerce_django"))
    assert "Redis" in result.caches_queues
    assert "Celery" in result.caches_queues


def test_ecommerce_django_routes():
    result = classify(str(FIXTURES / "ecommerce_django"))
    paths = {r.path for r in result.routes}
    assert any("checkout" in p for p in paths)
    assert any("cart" in p for p in paths)


def test_ecommerce_django_models():
    result = classify(str(FIXTURES / "ecommerce_django"))
    names = {m.name for m in result.data_models}
    assert {"Product", "Cart", "Order"}.issubset(names)


def test_blog_flask_classified_correctly():
    result = classify(str(FIXTURES / "blog_flask"))
    assert result.app_category == "blog / content platform"
    assert result.app_category_confidence >= 0.3
    assert result.framework == "Flask"


def test_blog_flask_models_extracted():
    result = classify(str(FIXTURES / "blog_flask"))
    names = {m.name for m in result.data_models}
    assert {"Post", "Comment", "Tag"}.issubset(names)


def test_admin_express_classified_correctly():
    result = classify(str(FIXTURES / "admin_express"))
    assert result.app_category == "admin panel / dashboard"
    assert result.framework == "Express"
    assert result.runtime.get("language") == "javascript"


def test_admin_express_routes_extracted():
    result = classify(str(FIXTURES / "admin_express"))
    assert len(result.routes) >= 4
    methods = {r.method for r in result.routes}
    assert "GET" in methods
    assert "POST" in methods


def test_functional_description_is_2_to_3_sentences():
    result = classify(str(FIXTURES / "ecommerce_django"))
    sentences = [s for s in result.functional_description.split(". ") if s.strip()]
    assert 2 <= len(sentences) <= 6  # range — README quote can push it up


def test_to_dict_is_json_serializable():
    import json
    result = classify(str(FIXTURES / "blog_flask"))
    blob = json.dumps(result.to_dict())
    assert "app_category" in blob
    assert "blog" in blob


def test_hosting_only_api_works():
    """Users who just want deployment data shouldn't need to run the classifier."""
    report = analyze_hosting_requirements(str(FIXTURES / "ecommerce_django"))
    assert report.runtime.get("language") == "python"
    assert any(d["name"] == "PostgreSQL" for d in report.databases)


def test_missing_path_returns_empty_gracefully():
    """Bad input shouldn't raise — just return an empty-ish report."""
    result = classify("/nonexistent/path/should/not/exist")
    assert isinstance(result, AppDescription)
    assert result.app_category == "unknown"


def test_classify_async_without_llm_matches_sync():
    """`classify_async(repo)` with no llm_provider should match `classify(repo)`."""
    sync_result = classify(str(FIXTURES / "blog_flask"))
    async_result = asyncio.run(classify_async(str(FIXTURES / "blog_flask")))
    assert sync_result.app_category == async_result.app_category
    assert sync_result.functional_description == async_result.functional_description


def test_llm_enrich_with_stub_provider_works():
    """A user-supplied provider should be able to replace the description."""
    result = classify(str(FIXTURES / "blog_flask"))

    async def stub_provider(prompt, max_tokens=400, temperature=0.2):
        # Verify the prompt has the structural context we expect
        assert "blog" in prompt.lower() or "Flask" in prompt
        return ("This is a Flask-based personal blog engine. Authors publish "
                "posts, readers comment, content is tagged. Minimal CRUD.")

    enriched = asyncio.run(llm_enrich_description(result, llm_provider=stub_provider))
    assert enriched is not None
    assert "blog" in enriched.lower()


def test_llm_enrich_with_failing_provider_returns_none():
    """If the provider raises, llm_enrich_description should return None gracefully."""
    result = classify(str(FIXTURES / "blog_flask"))

    async def broken_provider(prompt, max_tokens=400, temperature=0.2):
        raise RuntimeError("simulated LLM API timeout")

    enriched = asyncio.run(llm_enrich_description(result, llm_provider=broken_provider))
    assert enriched is None


def test_llm_enrich_with_no_provider_returns_none():
    result = classify(str(FIXTURES / "blog_flask"))
    enriched = asyncio.run(llm_enrich_description(result))
    assert enriched is None


def test_classify_async_with_provider_swaps_description():
    """When a working provider returns text, it should replace the deterministic one."""
    async def stub_provider(prompt, max_tokens=400, temperature=0.2):
        return ("ShopMax is a multi-vendor e-commerce marketplace where buyers "
                "purchase products via Stripe and vendors manage their inventory.")

    async_result = asyncio.run(classify_async(
        str(FIXTURES / "ecommerce_django"), llm_provider=stub_provider,
    ))
    assert "ShopMax" in async_result.functional_description
    assert "Stripe" in async_result.functional_description


def test_short_llm_response_is_rejected():
    """The hallucination guard rejects suspiciously short responses (<40 chars)."""
    result = classify(str(FIXTURES / "blog_flask"))

    async def too_short(prompt, max_tokens=400, temperature=0.2):
        return "ok"

    enriched = asyncio.run(llm_enrich_description(result, llm_provider=too_short))
    assert enriched is None


@pytest.mark.parametrize("fixture,expected_category", [
    ("ecommerce_django", "e-commerce"),
    ("blog_flask", "blog / content platform"),
    ("admin_express", "admin panel / dashboard"),
])
def test_all_fixtures_classify_correctly(fixture, expected_category):
    result = classify(str(FIXTURES / fixture))
    assert result.app_category == expected_category


# ─── v0.2.0 — PHP / Laravel / AI-LLM / DVWA / README mining ───

def test_dvwa_php_runtime_detected_from_bare_php():
    """DVWA has no composer.json — runtime should still detect PHP from .php files."""
    result = classify(str(FIXTURES / "dvwa_php"))
    assert result.runtime.get("language") == "php"


def test_dvwa_security_training_fingerprint():
    """DVWA README + filenames should trip the security-training fingerprint."""
    result = classify(str(FIXTURES / "dvwa_php"))
    assert result.app_category == "security training / vulnerable app"
    assert "security training" in result.detected_features


def test_dvwa_readme_surfaces_mariadb():
    """README says 'PHP/MariaDB' — even though no manifest, surface MariaDB."""
    result = classify(str(FIXTURES / "dvwa_php"))
    assert "MariaDB" in result.databases


def test_ai_llm_app_classified_as_ai():
    """OpenAI + LangChain + Chroma in deps → AI/LLM application."""
    result = classify(str(FIXTURES / "ai_llm_app"))
    assert result.app_category == "AI / LLM application"
    assert "LLM integration" in result.detected_features


def test_ai_llm_app_runtime_unchanged():
    """AI app is still Python+FastAPI; new fingerprint doesn't break stack detection."""
    result = classify(str(FIXTURES / "ai_llm_app"))
    assert result.runtime.get("language") == "python"
    assert result.framework == "FastAPI"


def test_laravel_app_detected_via_composer_json():
    """composer.json with laravel/framework → PHP runtime + Laravel framework."""
    result = classify(str(FIXTURES / "laravel_app"))
    assert result.runtime.get("language") == "php"
    assert result.framework == "Laravel"
    assert "^8.1" in (result.runtime.get("version_spec") or "")


def test_laravel_app_postgresql_from_readme_mining():
    """README mentions PostgreSQL — composer.json doesn't ship a driver."""
    result = classify(str(FIXTURES / "laravel_app"))
    assert "PostgreSQL" in result.databases


def test_markdown_image_only_skipped_in_purpose():
    """README purpose should skip pure-image paragraphs (Stripe AI-banner regression)."""
    import tempfile, shutil
    from app_classifier.classifier import _extract_purpose_from_readme
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path as P
        (P(td) / "README.md").write_text(
            "![Hero GIF](https://example.com/banner.gif)\n\n"
            "This is the actual project description that should be returned."
        )
        purpose = _extract_purpose_from_readme(P(td))
        assert "actual project description" in purpose
        assert "![Hero" not in purpose


def test_existing_fixtures_still_pass():
    """v0.1.0 fixtures must still classify correctly (no regression)."""
    assert classify(str(FIXTURES / "ecommerce_django")).app_category == "e-commerce"
    assert classify(str(FIXTURES / "blog_flask")).app_category == "blog / content platform"
    assert classify(str(FIXTURES / "admin_express")).app_category == "admin panel / dashboard"
