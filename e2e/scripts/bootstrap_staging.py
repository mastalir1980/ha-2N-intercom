#!/usr/bin/env python3
"""One-time (idempotent) setup of the staging Home Assistant on the Pi.

1. copies e2e/staging/{docker-compose.yml,configuration.yaml} to PI_STAGING_DIR
2. deploys the integration (working tree) and starts the container
3. onboards HA with an `e2e` user and stores a long-lived token in e2e/.env
4. creates the 2N config entry via the config flow REST API

Safe to re-run: every step checks whether it is already done.
"""

from __future__ import annotations

import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from e2elib import env  # noqa: E402
from e2elib.ha import DOMAIN, HA, HAError  # noqa: E402

E2E_DIR = env.E2E_DIR
CFG = env.load()


def need(key: str) -> str:
    val = CFG.get(key, "")
    if not val:
        sys.exit(f"missing {key} in e2e/.env")
    return val


def ssh(cmd: str, stdin: bytes | None = None) -> None:
    if need("PI_SSH") == "local":  # running on the Pi itself
        subprocess.run(["bash", "-c", cmd], input=stdin, check=True)
        return
    subprocess.run(["ssh", "-o", "BatchMode=yes", need("PI_SSH"), cmd], input=stdin, check=True)


def step_files() -> None:
    d = need("PI_STAGING_DIR")
    print(f"==> staging files -> {need('PI_SSH')}:{d}")
    ssh(f"mkdir -p '{d}/config'")
    ssh(f"cat > '{d}/docker-compose.yml'", (E2E_DIR / "staging/docker-compose.yml").read_bytes())
    ssh(f"cat > '{d}/config/configuration.yaml'", (E2E_DIR / "staging/configuration.yaml").read_bytes())


def step_deploy() -> None:
    subprocess.run(["bash", str(E2E_DIR / "scripts/deploy.sh"), "--worktree"], check=True)


def client_id(ha: HA) -> str:
    return ha.url + "/"


def exchange_code(ha: HA, code: str) -> str:
    r = requests.post(
        ha.url + "/auth/token",
        data={"grant_type": "authorization_code", "code": code, "client_id": client_id(ha)},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def step_auth(ha: HA) -> None:
    token = CFG.get("HA_TOKEN")
    if token:
        ha.token = token
        try:
            ha.config()
            print("==> HA token OK")
            return
        except HAError:
            print("==> stored HA_TOKEN invalid, creating a new one")

    r = requests.get(ha.url + "/api/onboarding", timeout=10)
    try:
        onboarding = r.json() if r.status_code == 200 else None
    except ValueError:
        onboarding = None
    # HA answers 404 / non-JSON once onboarding is finished
    user_done = any(s.get("step") == "user" and s.get("done") for s in onboarding) if isinstance(onboarding, list) else True
    password = CFG.get("HA_E2E_PASSWORD") or secrets.token_urlsafe(18)

    if not user_done:
        print("==> onboarding staging HA (user 'e2e')")
        r = requests.post(
            ha.url + "/api/onboarding/users",
            json={"client_id": client_id(ha), "name": "E2E", "username": "e2e", "password": password, "language": "en"},
            timeout=30,
        )
        r.raise_for_status()
        access = exchange_code(ha, r.json()["auth_code"])
        env.update_env_file({"HA_E2E_PASSWORD": password})
        hdr = {"Authorization": f"Bearer {access}"}
        for path, payload in (
            ("/api/onboarding/core_config", {}),
            ("/api/onboarding/analytics", {}),
            ("/api/onboarding/integration", {"client_id": client_id(ha), "redirect_uri": client_id(ha)}),
        ):
            requests.post(ha.url + path, json=payload, headers=hdr, timeout=15)  # best effort
    else:
        if not CFG.get("HA_E2E_PASSWORD"):
            sys.exit("staging HA is already onboarded but HA_E2E_PASSWORD is not in e2e/.env — "
                     "put it there (or wipe PI_STAGING_DIR/config/.storage) and re-run")
        print("==> logging in as 'e2e'")
        flow = requests.post(
            ha.url + "/auth/login_flow",
            json={"client_id": client_id(ha), "handler": ["homeassistant", None], "redirect_uri": client_id(ha)},
            timeout=15,
        ).json()
        res = requests.post(
            ha.url + f"/auth/login_flow/{flow['flow_id']}",
            json={"client_id": client_id(ha), "username": "e2e", "password": password},
            timeout=15,
        ).json()
        if res.get("type") != "create_entry":
            sys.exit(f"login failed: {res}")
        access = exchange_code(ha, res["result"])

    ha.token = access
    long_lived = ha.ws({"type": "auth/long_lived_access_token", "client_name": "2n-e2e", "lifespan": 3650})
    env.update_env_file({"HA_TOKEN": long_lived})
    ha.token = long_lived
    print("==> long-lived token stored in e2e/.env")


def step_entry(ha: HA) -> None:
    if ha.entries():
        print("==> 2N config entry already exists")
        return
    print("==> creating 2N config entry via config flow")
    answers = {
        "host": need("INTERCOM_HOST"),
        "username": need("INTERCOM_USER"),
        "password": need("INTERCOM_PASSWORD"),
        "name": "2N E2E",
        "enable_camera": True,
        "enable_doorbell": True,
    }
    res = ha.post_json("/api/config/config_entries/flow", {"handler": DOMAIN, "show_advanced_options": False})
    for _ in range(8):
        if res.get("type") == "create_entry":
            print(f"==> entry created: {res.get('title')}")
            return
        if res.get("type") != "form":
            sys.exit(f"config flow ended unexpectedly: {res}")
        if res.get("errors"):
            sys.exit(f"config flow step {res.get('step_id')} errors: {res['errors']}")
        payload = {}
        for field in res.get("data_schema", []):
            name = field["name"]
            if name in answers:
                payload[name] = answers[name]
            elif "default" in field:
                payload[name] = field["default"]
        print(f"    step {res.get('step_id')}: {sorted(payload)}")
        res = ha.post_json(f"/api/config/config_entries/flow/{res['flow_id']}", payload)
    sys.exit("config flow did not finish in 8 steps")


def main() -> None:
    env.assert_staging_url(need("HA_URL"))
    ha = HA(need("HA_URL"))
    step_files()
    step_deploy()
    ha.wait_up()
    step_auth(ha)
    step_entry(ha)
    print("==> staging ready. Run: bash e2e/e2e.sh run")


if __name__ == "__main__":
    main()
