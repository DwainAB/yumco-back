from __future__ import annotations

from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from main import app


ALLOWED_STATUS_CODES = {200, 201, 202, 204, 303, 400, 401, 403, 404, 422, 501}


def collect_routes() -> list[APIRoute]:
    routes: list[APIRoute] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
    return routes


def resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return resolve_schema(components[name], components)
    if "anyOf" in schema:
        non_null = [item for item in schema["anyOf"] if item.get("type") != "null"]
        return resolve_schema(non_null[0], components) if non_null else {}
    if "oneOf" in schema:
        return resolve_schema(schema["oneOf"][0], components)
    return schema


def example_for_name(name: str) -> Any:
    lowered = name.lower()
    if lowered.endswith("_id") or lowered == "id":
        return 1
    if lowered == "email":
        return "test@example.com"
    if lowered == "password":
        return "string"
    if lowered in {"role", "type"}:
        return "owner" if lowered == "role" else "pickup"
    if lowered == "status":
        return "pending"
    if lowered == "platform":
        return "ios"
    if lowered == "expo_push_token":
        return "ExponentPushToken[test]"
    if lowered in {"success_url", "cancel_url", "return_url", "refresh_url"}:
        return "https://example.com/callback"
    if "phone" in lowered:
        return "+33123456789"
    if "postal" in lowered:
        return "75001"
    if lowered == "country":
        return "FR"
    if lowered == "timezone":
        return "Europe/Paris"
    if lowered.endswith("_at") or "date" in lowered:
        return "2026-01-01T12:00:00Z" if lowered.endswith("_at") else "2026-01-01"
    if "price" in lowered or "amount" in lowered or "total" in lowered or "fee" in lowered or "subtotal" in lowered:
        return 12.5
    if lowered.startswith(("is_", "has_", "allow_", "notify_")):
        return True
    if "quota" in lowered or "count" in lowered or "remaining" in lowered or "people" in lowered or "party_size" in lowered:
        return 1
    return f"sample_{name}"


def example_from_schema(schema: dict[str, Any], components: dict[str, Any], prop_name: str | None = None) -> Any:
    schema = resolve_schema(schema, components)

    if "enum" in schema:
        return schema["enum"][0]

    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties", {})
        return {name: example_from_schema(value, components, name) for name, value in properties.items()}
    if schema_type == "array":
        item_schema = schema.get("items", {})
        return [example_from_schema(item_schema, components, prop_name)]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 12.5
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        if schema.get("format") == "binary":
            return b"file-content"
        if schema.get("format") == "email":
            return "test@example.com"
        if schema.get("format") == "uri":
            return "https://example.com"
        return example_for_name(prop_name or "value")
    return example_for_name(prop_name or "value")


def build_request(route: APIRoute, openapi: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    components = openapi.get("components", {}).get("schemas", {})
    method = next(iter(route.methods - {"HEAD", "OPTIONS"})).lower()
    schema_entry = openapi["paths"][route.path_format][method]

    path = route.path_format
    params: dict[str, Any] = {}
    headers = {"Authorization": "Bearer test-token"}

    for parameter in schema_entry.get("parameters", []):
        value = example_from_schema(parameter.get("schema", {}), components, parameter["name"])
        location = parameter["in"]
        if location == "path":
            path = path.replace(f"{{{parameter['name']}}}", str(value))
        elif location == "query":
            params[parameter["name"]] = value
        elif location == "header":
            headers[parameter["name"]] = str(value)

    request_kwargs: dict[str, Any] = {"params": params, "headers": headers}

    body = schema_entry.get("requestBody", {})
    content = body.get("content", {})
    if "application/json" in content:
        request_kwargs["json"] = example_from_schema(content["application/json"]["schema"], components)
    elif "multipart/form-data" in content:
        form_payload = example_from_schema(content["multipart/form-data"]["schema"], components)
        files: dict[str, Any] = {}
        data: dict[str, Any] = {}
        for key, value in form_payload.items():
            if isinstance(value, bytes):
                files[key] = ("upload.bin", value, "application/octet-stream")
            elif isinstance(value, list):
                data[key] = value
            else:
                data[key] = str(value)
        request_kwargs["data"] = data
        if files:
            request_kwargs["files"] = files
    elif "application/x-www-form-urlencoded" in content:
        request_kwargs["data"] = example_from_schema(content["application/x-www-form-urlencoded"]["schema"], components)

    return path, request_kwargs


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def test_cors_allows_dashboard_origin(client: TestClient) -> None:
    response = client.options(
        "/restaurants/1/stripe/connect/account",
        headers={
            "Origin": "https://dashboard.yumco.fr",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://dashboard.yumco.fr"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize(
    "route",
    collect_routes(),
    ids=lambda route: f"{next(iter(route.methods - {'HEAD', 'OPTIONS'}))} {route.path}",
)
def test_every_route_smoke(route: APIRoute, client: TestClient) -> None:
    openapi = app.openapi()
    method = next(iter(route.methods - {"HEAD", "OPTIONS"})).lower()
    path, request_kwargs = build_request(route, openapi)

    response = client.request(method.upper(), path, **request_kwargs)

    assert response.status_code in ALLOWED_STATUS_CODES, (
        f"Unexpected status for {method.upper()} {route.path}: "
        f"{response.status_code} with body {response.text}"
    )
