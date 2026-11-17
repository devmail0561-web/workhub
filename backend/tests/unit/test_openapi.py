from workhub.interfaces.rest.app import app


def test_error_responses_are_documented() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/health"]["get"]

    for status in ("401", "404", "405", "500"):
        response = operation["responses"][status]
        reference = response["content"]["application/json"]["schema"]["$ref"]
        assert reference == "#/components/schemas/ApiErrorResponse"

    assert "ApiErrorResponse" in schema["components"]["schemas"]


def test_auth_paths_are_documented_without_refresh_token_in_body() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/me" in paths
    token_schema = schema["components"]["schemas"]["TokenResponse"]
    assert "access_token" in token_schema["properties"]
    assert "refresh_token" not in token_schema["properties"]
