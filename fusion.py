"""
Author: M. Dijkens
Date last modified: 2026-10-22
License: MIT
Description: Async Fusion workflow client with automatic token reuse and safe errors.
"""
import asyncio
import base64
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlsplit

import httpx
from dotenv import dotenv_values


class FusionError(Exception):
    """A deliberately sanitized error suitable for the demo UI."""

    def __init__(self, code, message, stage="configuration", http_status=None):
        super().__init__(message)
        self.code, self.stage, self.http_status = code, stage, http_status

    def as_dict(self):
        """Return diagnostic fields without provider bodies or credentials."""
        return {"code": self.code, "message": str(self),
                "stage": self.stage, "httpStatus": self.http_status}


def derive_scope(hostname):
    """Derive the same scope as the already verified ODA component."""
    match = re.fullmatch(r"fa-(.+)-saasfademo\d+\.ds-fa\.oraclepdemos\.com", hostname, re.I)
    if match:
        pod = match[1]
    elif re.match(r"^[^.]+\.fa\.", hostname, re.I):
        pod = hostname.split(".")[0]
    else:
        raise FusionError("CONFIG_ERROR", "Cannot derive scope; set FUSION_SCOPE.")
    return f"urn:opc:resource:fusion:{pod}:fusion-ai/"


def token_expiry(token):
    """Decode JWT exp for scheduling only; Fusion verifies the signature."""
    try:
        part = token.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))["exp"]
        return float(exp) if not isinstance(exp, bool) and math.isfinite(float(exp)) else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


@dataclass(frozen=True, repr=False)
class Connection:
    """Immutable credentials; repr never exposes login values."""

    base_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    scope: str = ""

    def __repr__(self):
        return "Connection(values hidden)"

    def __post_init__(self):
        try:
            url = urlsplit(self.base_url)
            valid = (url.scheme == "https" and url.hostname and not url.username
                     and not url.password and url.path in ("", "/")
                     and not url.query and not url.fragment)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise FusionError("CONFIG_ERROR", "FUSION_BASE_URL must be an HTTPS origin.")
        for name in ("username", "password"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FusionError("CONFIG_ERROR", f"Missing FUSION_{name.upper()}.")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "scope", self.scope or derive_scope(url.hostname))

    @classmethod
    def from_env(cls, env_file=None, password_override=None):
        """Read a private dotenv file, with process settings taking precedence."""
        filename = Path(env_file) if env_file else Path(__file__).with_name(".env")
        values = {**dotenv_values(filename, interpolate=False), **os.environ}
        password = (password_override if password_override is not None
                    else values.get("FUSION_PASSWORD", ""))
        return cls(values.get("FUSION_BASE_URL", ""), values.get("FUSION_USERNAME", ""),
                   password, values.get("FUSION_SCOPE") or "")


class FusionClient:
    """One reusable async client and token cache per connection/worker."""

    def __init__(self, connection, *, transport=None, now=time.time, sleep=asyncio.sleep):
        self.connection = connection
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=False)
        self._now, self._sleep = now, sleep
        self._token, self._reuse_until = None, 0
        self._token_lock = asyncio.Lock()
        self.token_requests = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        """Close sockets and forget the cached token."""
        self._token, self._reuse_until = None, 0
        await self._http.aclose()

    async def _request(self, method, path, headers, body, deadline, stage):
        remaining = min(10.0, deadline - asyncio.get_running_loop().time())
        if remaining <= 0:
            raise FusionError("TIMEOUT", "Fusion call deadline exceeded.", stage)
        try:
            async with asyncio.timeout(remaining):
                response = await self._http.request(
                    method, self.connection.base_url + path,
                    headers={"Accept": "application/json", **headers},
                    json=body, timeout=remaining)
        except (TimeoutError, httpx.TimeoutException):
            raise FusionError("TIMEOUT", "Fusion request timed out.", stage) from None
        except httpx.HTTPError:
            raise FusionError("NETWORK_ERROR", "Fusion could not be reached.", stage) from None
        if not 200 <= response.status_code < 300:
            raise FusionError("HTTP_ERROR", f"Fusion returned HTTP {response.status_code}.",
                              stage, response.status_code)
        if len(response.content) > 2 * 1024 * 1024:
            raise FusionError("RESPONSE_ERROR", "Fusion response exceeded size limit.", stage)
        try:
            result = response.json()
        except ValueError:
            raise FusionError("RESPONSE_ERROR", "Fusion did not return valid JSON.", stage) from None
        if not isinstance(result, dict):
            raise FusionError("RESPONSE_ERROR", "Fusion did not return a JSON object.", stage)
        return result

    async def _get_token(self, deadline, rejected=None):
        async with self._token_lock:
            if rejected and self._token == rejected:
                self._token, self._reuse_until = None, 0
            if self._token and self._now() < self._reuse_until:
                return self._token
            self._token, self._reuse_until = None, 0
            c = self.connection
            basic = base64.b64encode(f"{c.username}:{c.password}".encode()).decode()
            self.token_requests += 1
            result = await self._request(
                "POST", "/crmRestApi/resources/latest/actionplans/action/getProcessAccessToken",
                {"Authorization": "Basic " + basic, "Override-Scope": c.scope,
                 "Content-Type": "application/vnd.oracle.adf.action+json"},
                {}, deadline, "token")
            token = result.get("result")
            if not isinstance(token, str) or not token.strip():
                raise FusionError("TOKEN_ERROR", "Fusion returned no token.", "token")
            expires = token_expiry(token)
            if expires is not None:
                lifetime = expires - self._now()
                if lifetime <= 0:
                    raise FusionError("TOKEN_ERROR", "Fusion returned an expired token.", "token")
                self._token = token
                self._reuse_until = expires - min(60, lifetime / 10)
            return token

    async def _call(self, method, path, body, deadline, stage):
        bearer = await self._get_token(deadline)
        for attempt in range(2):
            try:
                return await self._request(
                    method, path, {"Authorization": "Bearer " + bearer,
                                   "Content-Type": "application/json"},
                    body, deadline, stage)
            except FusionError as error:
                if error.http_status != 401 or attempt:
                    raise
                bearer = await self._get_token(deadline, rejected=bearer)

    async def call_agent(self, workflow, message=None, *, parameters=None,
                         conversation_id=None, job_id=None, wait_seconds=15):
        """Start or resume a workflow; return output/status/IDs without any token."""
        if not isinstance(workflow, str) or not workflow.strip():
            raise FusionError("CONFIG_ERROR", "A workflow code is required.")
        if not job_id and (not isinstance(message, str) or not message.strip()):
            raise FusionError("INPUT_ERROR", "A message is required for a new job.")
        if parameters is not None and not isinstance(parameters, dict):
            raise FusionError("INPUT_ERROR", "parameters must be an object.")
        if (isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float))
                or not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 20):
            raise FusionError("INPUT_ERROR", "wait_seconds must be between 0 and 20.")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 25
        path = "/api/fusion-ai/orchestrator/agent/v2/" + quote(workflow, safe="")
        if job_id:
            job = await self._call("GET", path + "/status/" + quote(str(job_id), safe=""),
                                   None, deadline, "status")
        else:
            body = {"message": message, "parameters": parameters or {}, "streamOutput": False}
            if conversation_id:
                body["conversationId"] = conversation_id
            job = await self._call("POST", path + "/invokeAsync", body, deadline, "invoke")
        identifier = job.get("jobId") or job_id
        if not isinstance(identifier, str) or not identifier:
            raise FusionError("RESPONSE_ERROR", "Fusion returned no jobId.", "invoke")
        conversation = job.get("conversationId") or conversation_id
        wait_until = min(loop.time() + wait_seconds, deadline - 1.5)
        while True:
            status = str(job.get("status") or "").upper()
            conversation = job.get("conversationId") or conversation
            if job.get("error") or status in {"FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"}:
                raise FusionError("WORKFLOW_ERROR", "Fusion workflow failed.", "status")
            if not status:
                raise FusionError("RESPONSE_ERROR", "Fusion returned no status.", "status")
            result = {"output": job.get("output") if status == "COMPLETE" else None,
                      "status": status, "jobId": identifier,
                      "conversationId": conversation, "workflow": workflow}
            if status == "COMPLETE" or loop.time() + 1 >= wait_until:
                return result
            await self._sleep(1)
            job = await self._call("GET", path + "/status/" + quote(identifier, safe=""),
                                   None, deadline, "status")

