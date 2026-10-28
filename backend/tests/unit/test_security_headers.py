from django.test import Client


def test_api_responses_forbid_loading_or_framing_anything():
    response = Client(HTTP_HOST="localhost").get("/healthz")
    assert response["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"


def test_the_api_docs_page_may_load_its_own_viewer_and_nothing_else():
    response = Client(HTTP_HOST="localhost").get("/api/v1/docs/")
    policy = response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in policy
    assert "default-src 'none'" in policy
    assert "script-src" in policy
