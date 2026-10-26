"""Author: M. Dijkens. Single-process UI, async backend and Streamable HTTP MCP."""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
from dotenv import dotenv_values
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route, Mount
from starlette.datastructures import Headers
from catalog import load_catalog
from fusion import FusionError
from runtime import Sessions
from eai import make_client, ask

ROOT = Path(__file__).resolve().parent
current_session = ContextVar("fusion_session", default=None)

def create_app(settings=None):
    values = settings if settings is not None else {**dotenv_values(ROOT/".env", interpolate=False), **os.environ}
    agents = load_catalog(values)
    sessions = Sessions(values)
    mcp = FastMCP("FusionMCP", mask_error_details=True)
    eai_client = None

    def register(agent):
        async def invoke(message: str = "", parameters: dict | None = None,
                         conversation_id: str | None = None, job_id: str | None = None) -> dict:
            session = current_session.get()
            if session is None: raise ToolError("A valid demo session is required.")
            try:
                return await session.client.call_agent(agent["workflow"], message, parameters=parameters,
                    conversation_id=conversation_id, job_id=job_id)
            except FusionError as error:
                raise ToolError(json.dumps(error.as_dict())) from None
        mcp.tool(invoke, name=agent["tool"], description=agent["description"])
    for agent in agents: register(agent)
    mcp_app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal eai_client
        eai_client = make_client(values)
        async with mcp_app.lifespan(app):
            try: yield
            finally:
                await sessions.close()
                await eai_client.close()

    async def health(request): return JSONResponse({"status":"ok"})
    async def ready(request): return JSONResponse({"status":"ready","agents":len(agents)})

    async def payload(request):
        if int(request.headers.get("content-length","0"))>32768:
            raise FusionError("INPUT_ERROR","Request is too large.")
        raw = await request.body()
        if len(raw)>32768: raise FusionError("INPUT_ERROR","Request is too large.")
        try: data=json.loads(raw)
        except ValueError: raise FusionError("INPUT_ERROR","Invalid JSON.") from None
        if not isinstance(data,dict): raise FusionError("INPUT_ERROR","Expected a JSON object.")
        return data

    async def login(request):
        try:
            data = await payload(request)
            password = data.get("password") or None
            if password is not None and not isinstance(password,str):
                raise FusionError("INPUT_ERROR","Password must be text.")
            token = await sessions.create(password)
            return JSONResponse({"token":token,"expiresIn":3600,
                "agents":[{"tool":a["tool"],"title":a["title"]} for a in agents],
                "eaiConfigured":bool(values.get("MCP_SERVER_URL"))})
        except FusionError as error: return JSONResponse({"error":error.as_dict()},status_code=400)

    def session_for(request):
        auth=request.headers.get("authorization","")
        return sessions.get(auth[7:]) if auth.startswith("Bearer ") else None

    async def chat(request):
        session=session_for(request)
        if session is None: return JSONResponse({"error":"Session expired. Connect again."},status_code=401)
        try:
            data=await payload(request)
            message=data.get("message")
            if not isinstance(message,str) or not message.strip() or len(message)>8000:
                raise FusionError("INPUT_ERROR","Enter a question of 1–8000 characters.")
            agent=next((a for a in agents if a["tool"]==data.get("agent")),None)
            if agent is None: raise FusionError("INPUT_ERROR","Select a configured agent.")
            mode=data.get("mode","eai")
            if mode not in ("eai","direct"): raise FusionError("INPUT_ERROR","Unknown call mode.")
            async with session.lock:
                if mode=="eai":
                    call_settings = values
                    candidate = data.get("mcpUrl", "")
                    if not values.get("MCP_SERVER_URL") and isinstance(candidate, str):
                        from urllib.parse import urlsplit
                        parsed = urlsplit(candidate)
                        expected = {f"{prefix}.generativeai.{values['GENAI_REGION']}.oci.oraclecloud.com"
                                    for prefix in ("application", "inference")}
                        if parsed.scheme == "https" and parsed.hostname in expected and parsed.path.endswith("/actions/invoke/mcp") and not parsed.query and not parsed.fragment:
                            call_settings = {**values, "MCP_SERVER_URL": candidate}
                    result=await ask(eai_client,call_settings,agent,message,request.headers["authorization"][7:])
                    result["route"]="EAI → MCP → Fusion"
                else:
                    job=await session.client.call_agent(agent["workflow"],message)
                    for _ in range(3):
                        if job["status"]=="COMPLETE": break
                        job=await session.client.call_agent(agent["workflow"],job_id=job["jobId"],conversation_id=job["conversationId"])
                    result={"answer":job["output"],"route":"Direct Fusion test","status":job["status"],
                            "evidence":[{"type":"fusion_job","status":job["status"]}]}
                result["tokenAcquisitions"]=session.client.token_requests
                return JSONResponse(result)
        except FusionError as error: return JSONResponse({"error":error.as_dict()},status_code=502)

    async def index(request): return FileResponse(ROOT/"static"/"index.html")

    inner=Starlette(lifespan=lifespan,routes=[Route("/",index),Route("/health",health),Route("/ready",ready),
          Route("/api/session",login,methods=["POST"]),Route("/api/chat",chat,methods=["POST"]),
          Mount("/",app=mcp_app)])

    class Guard:
        def __init__(self, app): self.app=app
        async def __call__(self, scope, receive, send):
            if scope["type"]!="http": return await self.app(scope,receive,send)
            headers=Headers(scope=scope)
            if scope["method"]=="POST":
                origin=headers.get("origin")
                if origin:
                    from urllib.parse import urlsplit
                    oci_origins = {f"https://{prefix}.generativeai.{values['GENAI_REGION']}.oci.oraclecloud.com"
                                   for prefix in ("application", "inference")}
                    if urlsplit(origin).netloc != headers.get("host") and origin not in oci_origins:
                        return await JSONResponse({"error":"Origin rejected."},403)(scope,receive,send)
            context=None
            if scope["path"].startswith("/mcp"):
                auth=headers.get("authorization","")
                session=sessions.get(auth[7:]) if auth.startswith("Bearer ") else None
                if session is None:
                    return await JSONResponse({"error":"Valid demo session required."},401)(scope,receive,send)
                context=current_session.set(session)
            async def safe_send(message):
                if message["type"]=="http.response.start":
                    message["headers"] += [(b"cache-control",b"no-store"),(b"x-content-type-options",b"nosniff")]
                await send(message)
            try: await self.app(scope,receive,safe_send)
            finally:
                if context is not None: current_session.reset(context)
    return Guard(inner)

if __name__=="__main__":
    import uvicorn
    uvicorn.run(create_app(),host="0.0.0.0",port=int(os.environ.get("PORT","8080")),access_log=False,log_level="warning")

