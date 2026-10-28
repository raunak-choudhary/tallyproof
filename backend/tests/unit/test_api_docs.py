from django.test import Client


def test_the_api_docs_page_renders_with_a_pinned_viewer():
    response = Client(HTTP_HOST="localhost").get("/api/v1/docs/")
    assert response.status_code == 200
    page = response.content.decode()
    assert "swagger-ui-dist@" in page
    assert "swagger-ui-dist@latest" not in page
