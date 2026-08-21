"""Frontend-facing API contract tests."""


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_frontend_cors_preflight(client):
    response = client.options(
        "/api/verify",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_upload_pdf(client):
    response = client.post(
        "/api/parse",
        files={"file": ("paper.pdf", b"%PDF-1.4\ntest content", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["file_type"] == "pdf"
    assert body["status"] == "pending"
    assert body["title"] == "paper"
    assert body["paper_id"]


def test_upload_bib(client):
    response = client.post(
        "/api/parse",
        files={"file": ("references.bib", b"@article{demo, title={Demo}}", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["file_type"] == "bib"


def test_rejects_unsupported_file(client):
    response = client.post(
        "/api/parse",
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )

    assert response.status_code == 415


def test_rejects_empty_file(client):
    response = client.post(
        "/api/parse",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400


def test_verify_returns_frontend_contract(client):
    response = client.post(
        "/api/verify",
        json={
            "claim": "Self-attention removes the need for recurrence.",
            "source_paper_id": "paper-attention",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "SUPPORT"
    assert body["confidence"] > 0
    assert body["matches"]
    assert body["matches"][0]["passage_text"]


def test_verify_rejects_empty_claim(client):
    response = client.post(
        "/api/verify",
        json={"claim": "   ", "source_paper_id": "paper-attention"},
    )

    assert response.status_code == 400


def test_audit_returns_consistent_non_empty_result(client):
    response = client.post(
        "/api/audit",
        json={
            "manuscript_id": "transformer-survey.pdf",
            "source_paper_ids": ["paper-attention", "paper-bert"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_citations"] == 2
    assert len(body["results"]) == 2
    assert (
        body["supported"]
        + body["partial"]
        + body["contradicted"]
        + body["not_found"]
        == body["total_citations"]
    )


def test_audit_rejects_empty_sources(client):
    response = client.post(
        "/api/audit",
        json={"manuscript_id": "manuscript.pdf", "source_paper_ids": []},
    )

    assert response.status_code == 400
