"""Explicit live test: real MCP protocol -> real Fusion, with private local settings."""
from pathlib import Path
import os
from dotenv import dotenv_values
from starlette.testclient import TestClient
from server import create_app

def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    settings={**dotenv_values(Path(__file__).with_name(".env"),interpolate=False),**os.environ}
    with TestClient(create_app(settings)) as client:
        login=client.post("/api/session",json={})
        if login.status_code!=200:
            print("Session creation failed (details hidden)."); return 1
        token=login.json()["token"]
        headers={"Authorization":"Bearer "+token,"Accept":"application/json, text/event-stream"}
        tool=login.json()["agents"][0]["tool"]
        for index in range(2):
            r=client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":index+1,
                "method":"tools/call","params":{"name":tool,"arguments":{"message":"Reply with exactly: MCP OK"}}})
            data=r.json().get("result",{})
            if r.status_code!=200 or data.get("isError") or "error" in r.json():
                print("MCP call failed (details hidden)."); return 1
            structured=data.get("structuredContent") or {}
            if not structured:
                content=data.get("content",[])
                structured=__import__("json").loads(content[0]["text"])
            print("MCP run",index+1,":",structured.get("status"))
            print(structured.get("output") or "(pending)")
            if structured.get("status")!="COMPLETE": return 2
    print("Real MCP tools/call -> Fusion succeeded twice. No remote EAI callback was tested.")
    return 0
if __name__=="__main__": raise SystemExit(main())

