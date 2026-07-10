"""Tests for Mentis V1 API endpoint registration & schema."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'ok'


def test_openapi_schema_includes_v1_routes():
    """Verify V1 endpoints appear in the OpenAPI schema."""
    schema = client.get('/openapi.json').json()
    paths = schema.get('paths', {})

    assert '/api/v1/teach/doubt' in paths, 'teach/doubt not in schema'
    assert '/api/v1/teach/lesson' in paths, 'teach/lesson not in schema'
    assert '/api/v1/teach/doubt/image' in paths, 'teach/doubt/image not in schema'


def test_health_route_in_schema():
    schema = client.get('/openapi.json').json()
    assert '/health' in schema.get('paths', {})


def test_v1_route_methods():
    schema = client.get('/openapi.json').json()
    paths = schema['paths']

    doubt_paths = paths['/api/v1/teach/doubt']
    assert 'post' in doubt_paths

    lesson_paths = paths['/api/v1/teach/lesson']
    assert 'post' in lesson_paths

    image_paths = paths['/api/v1/teach/doubt/image']
    assert 'post' in image_paths


def test_legacy_routes_still_registered():
    """Ensure we didn't break existing routes."""
    schema = client.get('/openapi.json').json()
    paths = schema.get('paths', {})
    legacy_routes = [
        '/api/tutor/recognize',
        '/api/tutor/lesson',
        '/api/tutor/doubt',
        '/api/auth/set-password',
    ]
    for route in legacy_routes:
        assert route in paths, f'Legacy route {route} missing from schema'
