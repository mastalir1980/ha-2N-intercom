"""Shared test helpers and stubs for the 2N Intercom unit tests.

This module exists to dedupe the boilerplate that every ``test_*.py`` file
needs in order to load integration sources without a real Home Assistant or
``aiohttp`` install.

The unit tests use ``unittest.IsolatedAsyncioTestCase`` (not pytest), so
``conftest.py`` is not auto-loaded — each test module imports the pieces it
needs from ``_stubs`` explicitly. ``unittest discover -s tests -t tests``
puts the ``tests`` directory on ``sys.path``, which is what makes the import
work from sibling files.

What lives here:
    * filesystem layout constants (``REPO_ROOT`` and the source paths)
    * ``ensure_package`` and ``load_module`` helpers
    * ``install_api_stubs`` — registers fake ``aiohttp`` and ``async_timeout``
      modules so ``custom_components.2n_intercom.api`` can be imported

What does NOT live here:
    * The Home Assistant component stubs. Each test file stubs only the HA
      modules it actually exercises (camera, lock, sensor, ...) and those
      vary widely between files. Pulling them all into one mega-stub creates
      cross-test coupling without saving meaningful LOC.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "2n_intercom"

API_PATH = INTEGRATION_DIR / "api.py"
CONST_PATH = INTEGRATION_DIR / "const.py"
COORDINATOR_PATH = INTEGRATION_DIR / "coordinator.py"
ENTITY_PATH = INTEGRATION_DIR / "entity.py"
INIT_PATH = INTEGRATION_DIR / "__init__.py"
CAMERA_PATH = INTEGRATION_DIR / "camera.py"
SENSOR_PATH = INTEGRATION_DIR / "sensor.py"
LOCK_PATH = INTEGRATION_DIR / "lock.py"
BINARY_SENSOR_PATH = INTEGRATION_DIR / "binary_sensor.py"
CONFIG_FLOW_PATH = INTEGRATION_DIR / "config_flow.py"
COVER_PATH = INTEGRATION_DIR / "cover.py"
SWITCH_PATH = INTEGRATION_DIR / "switch.py"
IMAGE_PATH = INTEGRATION_DIR / "image.py"
DIAGNOSTICS_PATH = INTEGRATION_DIR / "diagnostics.py"


def ensure_package(name: str) -> types.ModuleType:
    """Create an empty namespace package in ``sys.modules`` if missing."""

    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a Python file as ``module_name`` and register it in ``sys.modules``."""

    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def install_api_stubs() -> None:
    """Register fake ``aiohttp`` + ``async_timeout`` modules.

    The integration's ``api.py`` imports these at module level, so they must
    be present in ``sys.modules`` *before* ``api.py`` is loaded.
    """

    aiohttp = types.ModuleType("aiohttp")

    class BasicAuth:
        def __init__(self, login: str, password: str) -> None:
            self.login = login
            self.password = password

    class TCPConnector:
        def __init__(self, ssl: bool) -> None:
            self.ssl = ssl
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class ClientSession:
        def __init__(self, *args, **kwargs) -> None:
            self.connector = kwargs.get("connector", TCPConnector(ssl=True))

        @property
        def closed(self):
            return self.connector is None or self.connector.closed

        async def close(self) -> None:
            if self.connector is not None:
                await self.connector.close()
            self.detach()

        def detach(self) -> None:
            self.connector = None

    class ClientResponse:
        status = 200
        headers: dict[str, str] = {}

    class ClientError(Exception):
        """Stub aiohttp client error."""

    def digest_auth_middleware(*args, **kwargs):
        return object()

    aiohttp.BasicAuth = BasicAuth
    aiohttp.TCPConnector = TCPConnector
    aiohttp.ClientSession = ClientSession
    aiohttp.ClientResponse = ClientResponse
    aiohttp.ClientError = ClientError
    aiohttp.DigestAuthMiddleware = digest_auth_middleware
    sys.modules["aiohttp"] = aiohttp

    async_timeout = types.ModuleType("async_timeout")

    class _Timeout:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def timeout(*args, **kwargs):
        return _Timeout()

    async_timeout.timeout = timeout
    sys.modules["async_timeout"] = async_timeout


def install_dt_util_stub() -> types.ModuleType:
    """Register a minimal ``homeassistant.util.dt`` (tz-aware helpers)."""

    from datetime import datetime, timezone

    ensure_package("homeassistant")
    util = ensure_package("homeassistant.util")
    existing = sys.modules.get("homeassistant.util.dt")
    if existing is not None:
        return existing

    dt_module = types.ModuleType("homeassistant.util.dt")
    dt_module.UTC = timezone.utc

    def utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def now() -> datetime:
        return datetime.now(timezone.utc)

    def utc_from_timestamp(timestamp: float) -> datetime:
        return datetime.fromtimestamp(timestamp, timezone.utc)

    dt_module.utcnow = utcnow
    dt_module.now = now
    dt_module.utc_from_timestamp = utc_from_timestamp
    util.dt = dt_module  # type: ignore[attr-defined]
    sys.modules["homeassistant.util.dt"] = dt_module
    return dt_module
