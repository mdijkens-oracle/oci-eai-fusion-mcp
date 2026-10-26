"""HTTP and real MCP protocol tests without calling any external service."""
import json
import unittest
from unittest.mock import patch
from starlette.testclient import TestClient
from server import create_app

SETTINGS={"FUSION_BASE_URL":"https://demo.fa.example.com",
          "FUSION_USERNAME":"user","FUSION_PASSWORD":"secret","FUSION_WORKFLOW":"TEST",
          "GENAI_REGION":"eu-frankfurt-1","GENAI_PROJECT_ID":"project","GENAI_API_KEY":"fake-key","GENAI_MODEL":"fake"}
class FakeFusion:
    def __init__(self,connection): self.connection=connection; self.token_requests=1
    async def aclose(self): pass
    async def call_agent(self,workflow,message=None,**kwargs):
        return {"output":"FROM "+self.connection.password, "status":"COMPLETE","jobId":"job","conversationId":"c","workflow":workflow}

class ServerTests(unittest.TestCase):
    def rpc(self,client,token,method,params):
        r=client.post("/mcp",headers={"Authorization":"Bearer "+token,
             "Accept":"application/json, text/event-stream"},
             json={"jsonrpc":"2.0","id":1,"method":method,"params":params})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def test_anonymous_session_schema_and_isolation(self):
        with patch("runtime.FusionClient",FakeFusion),TestClient(create_app(SETTINGS)) as c:
            self.assertEqual(c.get("/health").json()["status"],"ok")
            self.assertEqual(c.post("/api/session",json={}).status_code,200)
            self.assertEqual(c.post("/mcp",json={}).status_code,401)
            tokens=[]
            for password in ("one","two"):
                r=c.post("/api/session",json={"password":password})
                self.assertEqual(r.status_code,200,r.text)
                tokens.append(r.json()["token"])
            listed=self.rpc(c,tokens[0],"tools/list",{})["result"]["tools"]
            self.assertEqual([t["name"] for t in listed],["ask_fusion_agent"])
            schema=json.dumps(listed)
            self.assertNotIn("password",schema)
            self.assertNotIn("secret",schema)
            for token,password in zip(tokens,("one","two")):
                result=self.rpc(c,token,"tools/call",{"name":"ask_fusion_agent","arguments":{"message":"hello"}})
                self.assertNotIn("error",result,result)
                self.assertIn("FROM "+password,json.dumps(result))
            direct=c.post("/api/chat",headers={"Authorization":"Bearer "+tokens[0]},
                          json={"agent":"ask_fusion_agent","message":"hello","mode":"direct"})
            self.assertEqual(direct.json()["answer"],"FROM one")

    def test_documented_inference_host_callback(self):
        from unittest.mock import AsyncMock
        mocked=AsyncMock(return_value={"answer":"OK","evidence":[{"type":"mcp_call"}]})
        url="https://inference.generativeai.eu-frankfurt-1.oci.oraclecloud.com/20251112/hostedApplications/test/actions/invoke/mcp"
        with patch("runtime.FusionClient",FakeFusion),patch("server.ask",mocked),TestClient(create_app(SETTINGS)) as c:
            token=c.post("/api/session",json={}).json()["token"]
            r=c.post("/api/chat",headers={"Authorization":"Bearer "+token},json={
                "agent":"ask_fusion_agent","message":"hello","mode":"eai","mcpUrl":url})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(mocked.call_args.args[1]["MCP_SERVER_URL"],url)


    def test_hosted_proxy_origin(self):
        origin="https://inference.generativeai.eu-frankfurt-1.oci.oraclecloud.com"
        with patch("runtime.FusionClient",FakeFusion),TestClient(create_app(SETTINGS)) as c:
            result=c.post("/api/session",json={},
                          headers={"Host":"internal-proxy:8080","Origin":origin})
            self.assertEqual(result.status_code,200,result.text)

    def test_invalid_input_and_origin(self):
        with patch("runtime.FusionClient",FakeFusion),TestClient(create_app(SETTINGS)) as c:
            self.assertEqual(c.post("/api/session",json={},headers={"Origin":"https://elsewhere.example"}).status_code,403)
            token=c.post("/api/session",json={}).json()["token"]
            r=c.post("/api/chat",headers={"Authorization":"Bearer "+token},json={"message":"","agent":"ask_fusion_agent"})
            self.assertEqual(r.status_code,502)
            self.assertEqual(r.json()["error"]["code"],"INPUT_ERROR")
            self.assertEqual(c.get("/").headers["cache-control"],"no-store")

