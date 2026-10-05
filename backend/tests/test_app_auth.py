import base64
import json
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from services.app_auth import require_user, require_snapshot_token, AppAuthorizationMiddleware


def request(headers=None, client="127.0.0.1", host="localhost", method="GET"):
    return Request({"type": "http", "method": method, "path": "/api/example",
                    "scheme": "http", "server": (host, 80), "client": (client, 1234),
                    "query_string": b"", "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()]})


def principal(email="wilson.sgroi@key-stone.it", provider="aad"):
    return base64.b64encode(json.dumps({"identityProvider": provider, "userId": "user-id",
                                       "userRoles": ["authenticated"], "userDetails": email}).encode()).decode()


class AppAuthTests(unittest.TestCase):
    def test_local_browser_cannot_trigger_a_write_from_an_external_site(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                require_user(request({"origin": "https://example.com"}, method="POST"))
            self.assertEqual(caught.exception.status_code, 403)

    def test_snapshot_auth_exception_does_not_trust_forged_user_headers(self):
        app = FastAPI()
        app.add_middleware(AppAuthorizationMiddleware)
        @app.get("/api/mc-code/snapshot")
        def snapshot():
            return {"private": True}
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "app", "APP_AUTH_MODE": "linked",
                                   "APP_AUTH_GATEWAY_ENABLED": "true", "MC_CODE_SNAPSHOT_TOKEN": "publisher-secret"}, clear=True):
            with TestClient(app) as client:
                response = client.get("/api/mc-code/snapshot", headers={"x-ms-client-principal": principal()})
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("private", response.json())

    def test_local_bypass_requires_loopback_connection(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(require_user(request()), "local@dev")
            with self.assertRaises(HTTPException) as caught:
                require_user(request(client="192.168.1.10"))
            self.assertEqual(caught.exception.status_code, 403)

    def test_cloud_does_not_accept_a_forged_header_without_gateway(self):
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "luciana-backend"}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                require_user(request({"x-ms-client-principal": principal()}))
            self.assertEqual(caught.exception.status_code, 503)

    def test_gateway_rejects_missing_identity_other_provider_and_outside_user(self):
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "app", "APP_AUTH_MODE": "linked", "APP_AUTH_GATEWAY_ENABLED": "true"}, clear=True):
            for headers, status in [({}, 401), ({"x-ms-client-principal": "not-base64"}, 401),
                                    ({"x-ms-client-principal": principal(provider="github")}, 401),
                                    ({"x-ms-client-principal": principal(email="user@example.com")}, 403)]:
                with self.subTest(headers=headers):
                    with self.assertRaises(HTTPException) as caught:
                        require_user(request(headers))
                    self.assertEqual(caught.exception.status_code, status)
            self.assertEqual(require_user(request({"x-ms-client-principal": principal()})), "wilson.sgroi@key-stone.it")

    def test_snapshot_requires_its_own_token(self):
        with patch.dict(os.environ, {"CODEX_SNAPSHOT_TOKEN": "test-snapshot-token"}, clear=True):
            with self.assertRaises(HTTPException):
                require_snapshot_token(request())
            self.assertEqual(require_snapshot_token(request({"x-codex-snapshot-token": "test-snapshot-token"})), "snapshot-publisher")

    def test_cross_origin_write_is_rejected(self):
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "app", "APP_AUTH_MODE": "linked", "APP_AUTH_GATEWAY_ENABLED": "true"}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                require_user(request({"x-ms-client-principal": principal(), "origin": "https://example.com"}, method="POST"))
            self.assertEqual(caught.exception.status_code, 403)
