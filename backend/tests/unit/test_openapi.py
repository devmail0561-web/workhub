from workhub.interfaces.rest.app import app


def test_error_responses_are_documented() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/health"]["get"]

    for status in ("404", "405", "500"):
        response = operation["responses"][status]
        reference = response["content"]["application/json"]["schema"]["$ref"]
        assert reference == "#/components/schemas/ApiErrorResponse"

    assert "ApiErrorResponse" in schema["components"]["schemas"]
