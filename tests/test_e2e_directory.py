"""Offline regression tests for the independent E2E directory client."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, call, patch, sentinel

from _stubs import REPO_ROOT, load_module


class DirectoryClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests = types.ModuleType("requests")
        self.requests.post = Mock()
        auth = types.ModuleType("requests.auth")
        auth.HTTPBasicAuth = Mock(return_value=sentinel.basic_auth)
        auth.HTTPDigestAuth = Mock(return_value=sentinel.digest_auth)
        with patch.dict(sys.modules, {
            "requests": self.requests,
            "requests.auth": auth,
            "urllib3": types.ModuleType("urllib3"),
        }):
            module = load_module(
                "e2e_directory_client_test",
                REPO_ROOT / "e2e" / "e2elib" / "twon.py",
            )
        self.client = module.TwoN(
            "example.invalid", "test-user", "test-password", verify=True
        )

    def _response(self, body, *, status=200, headers=None):
        response = Mock(status_code=status, headers=headers or {})
        response.json.return_value = body
        return response

    def test_directory_query_selects_name_and_keeps_uuid_metadata(self) -> None:
        users = [{"uuid": "USER-1", "name": "Alice", "timestamp": 1}]
        response = self._response({"success": True, "result": {"users": users}})
        self.requests.post.return_value = response

        self.assertEqual(self.client.dir_users(), users)
        self.requests.post.assert_called_once_with(
            "https://example.invalid/api/dir/query",
            auth=sentinel.digest_auth,
            json={"iterator": {"timestamp": 0}, "fields": ["name"]},
            verify=True,
            timeout=10,
        )
        response.raise_for_status.assert_called_once_with()

    def test_directory_basic_retry_preserves_the_query(self) -> None:
        challenge = self._response(
            {}, status=401, headers={"WWW-Authenticate": 'Basic realm="Directory"'}
        )
        users = [{"uuid": "USER-1", "name": "Alice"}]
        response = self._response({"success": True, "result": {"users": users}})
        self.requests.post.side_effect = [challenge, response]

        self.assertEqual(self.client.dir_users(), users)
        kwargs = {
            "json": {"iterator": {"timestamp": 0}, "fields": ["name"]},
            "verify": True,
            "timeout": 10,
        }
        self.assertEqual(self.requests.post.call_args_list, [
            call(
                "https://example.invalid/api/dir/query",
                auth=sentinel.digest_auth,
                **kwargs,
            ),
            call(
                "https://example.invalid/api/dir/query",
                auth=sentinel.basic_auth,
                **kwargs,
            ),
        ])
        challenge.json.assert_not_called()

    def test_directory_device_error_reports_only_numeric_code(self) -> None:
        self.requests.post.return_value = self._response({
            "success": False,
            "error": {
                "code": 12,
                "description": "private directory data",
                "param": "private parameter value",
            },
        })

        with self.assertRaises(RuntimeError) as ctx:
            self.client.dir_users()
        self.assertEqual(str(ctx.exception), "2N /api/dir/query failed (code 12)")
        self.requests.post.assert_called_once()

    def test_directory_error_without_numeric_code_still_fails_privately(self) -> None:
        for error in (None, "private data", {"code": "private data"}):
            with self.subTest(error=error):
                self.requests.post.return_value = self._response({
                    "success": False,
                    "error": error,
                })
                with self.assertRaises(RuntimeError) as ctx:
                    self.client.dir_users()
                self.assertEqual(str(ctx.exception), "2N /api/dir/query failed")

    def test_directory_http_error_is_not_treated_as_empty_directory(self) -> None:
        response = self._response({}, status=403)
        response.raise_for_status.side_effect = RuntimeError("HTTP 403")
        self.requests.post.return_value = response

        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            self.client.dir_users()
        response.json.assert_not_called()
