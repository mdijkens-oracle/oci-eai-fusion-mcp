"""Author: M. Dijkens. OCI Responses API with real remote MCP tool evidence."""
from urllib.parse import urlsplit
from openai import AsyncOpenAI, APIError
from fusion import FusionError

def make_client(settings):
    return AsyncOpenAI(
        base_url=f"https://inference.generativeai.{settings['GENAI_REGION']}.oci.oraclecloud.com/openai/v1",
        api_key=settings["GENAI_API_KEY"], project=settings["GENAI_PROJECT_ID"],
        timeout=120, max_retries=0)

async def ask(client, settings, agent, message, session_token):
    url = settings.get("MCP_SERVER_URL","")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise FusionError("MCP_URL_REQUIRED", "A public HTTPS MCP_SERVER_URL is required for EAI. Direct Fusion testing works locally.", "eai")
    try:
        response = await client.responses.create(
            model=settings["GENAI_MODEL"],
            instructions=(f"Always call {agent['tool']} on the fusion MCP server with the user's exact question. "
                          "If its status is pending, resume using its job_id. "
                          "Report tool errors honestly; do not invent a Fusion answer."),
            input=f"Use the MCP tool {agent['tool']} to answer this question. Pass the exact question as its message argument:\n{message}",
            tools=[{"type":"mcp", "server_label":"fusion",
                    "server_url":url, "authorization":session_token,
                    "allowed_tools":[agent["tool"]], "require_approval":"never"}],
            store=False)
    except APIError as error:
        raise FusionError("EAI_ERROR", "OCI Responses API request failed. Check the configured key, project, model and public MCP URL.",
                          "eai", getattr(error,"status_code",None)) from None
    evidence = []
    for item in response.output:
        kind = getattr(item,"type","")
        if kind in ("mcp_call","mcp_list_tools"):
            evidence.append({"type":kind, "name":getattr(item,"name",None),
                             "status":getattr(item,"status",None),
                             "error":bool(getattr(item,"error",None))})
    calls = [e for e in evidence if e["type"]=="mcp_call"]
    if not calls or any(e["error"] for e in calls):
        raise FusionError("MCP_NOT_COMPLETED", "EAI did not complete a successful MCP tool call. No Fusion success is claimed.", "mcp")
    return {"answer":response.output_text, "evidence":evidence}

