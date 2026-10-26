"""Offline tests for Fusion token lifecycle and asynchronous workflow calls."""
import asyncio
import base64
import json
import unittest
import httpx
from fusion import Connection, FusionClient, FusionError, derive_scope

def jwt(exp):
    return "header." + base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=") + ".signature"

class FusionTests(unittest.IsolatedAsyncioTestCase):
    def connection(self):
        return Connection("https://demo.fa.example.com", "demo", "private-password")

    async def test_parallel_calls_share_token_and_poll(self):
        tokens = []
        async def handler(request):
            if "getProcessAccessToken" in request.url.path:
                tokens.append(1)
                self.assertEqual(request.headers["Content-Type"], "application/vnd.oracle.adf.action+json")
                self.assertEqual(request.headers["Override-Scope"], "urn:opc:resource:fusion:demo:fusion-ai/")
                return httpx.Response(200, json={"result": jwt(2000)})
            if request.method == "POST":
                return httpx.Response(200, json={"jobId": "job", "status": "RUNNING"})
            self.assertEqual(request.content, b"")
            return httpx.Response(200, json={"jobId": "job", "status": "COMPLETE", "output": "OK"})
        async def no_sleep(_): pass
        async with FusionClient(self.connection(), transport=httpx.MockTransport(handler), now=lambda:1000, sleep=no_sleep) as c:
            results = await asyncio.gather(*(c.call_agent("TEST", "Hello") for _ in range(3)))
            self.assertTrue(all(r["output"] == "OK" for r in results))
            self.assertEqual(len(tokens), 1)

    async def test_401_renews_once(self):
        tokens, invocations = [], []
        def handler(request):
            if "getProcessAccessToken" in request.url.path:
                tokens.append(1)
                return httpx.Response(200, json={"result": jwt(2000+len(tokens))})
            invocations.append(1)
            if len(invocations)==1: return httpx.Response(401, text="secret provider body")
            return httpx.Response(200, json={"jobId":"j","status":"COMPLETE","output":"OK"})
        async with FusionClient(self.connection(), transport=httpx.MockTransport(handler), now=lambda:1000) as c:
            self.assertEqual((await c.call_agent("TEST","Hello"))["output"],"OK")
            self.assertEqual(c.token_requests,2)

    async def test_expiry_refresh_and_resume_no_submit(self):
        clock=[1000]
        def handler(request):
            if "getProcessAccessToken" in request.url.path:
                return httpx.Response(200,json={"result":jwt(clock[0]+100)})
            self.assertEqual(request.method,"GET")
            return httpx.Response(200,json={"jobId":"j","status":"COMPLETE","output":"OK"})
        async with FusionClient(self.connection(),transport=httpx.MockTransport(handler),now=lambda:clock[0]) as c:
            await c.call_agent("TEST",job_id="j")
            clock[0]+=95
            await c.call_agent("TEST",job_id="j")
            self.assertEqual(c.token_requests,2)

    async def test_errors_are_sanitized(self):
        def handler(request): return httpx.Response(403,text="private-password SECRET_TOKEN")
        async with FusionClient(self.connection(),transport=httpx.MockTransport(handler)) as c:
            with self.assertRaises(FusionError) as error: await c.call_agent("TEST","Hello")
            self.assertNotIn("private-password",json.dumps(error.exception.as_dict()))
            self.assertEqual(error.exception.http_status,403)
        self.assertNotIn("private-password",repr(self.connection()))

    def test_scope(self):
        self.assertEqual(derive_scope("fa-demo-dev1-saasfademo1.ds-fa.oraclepdemos.com"),"urn:opc:resource:fusion:demo-dev1:fusion-ai/")
        with self.assertRaises(FusionError): Connection("http://example.com","u","p")

