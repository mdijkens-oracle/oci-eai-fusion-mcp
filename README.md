# OCI Enterprise AI to Fusion AI Agent Studio via MCP

Connect OCI Enterprise AI to an existing Oracle Fusion AI Agent Studio workflow
through a remote MCP tool. This demo includes a browser page, a Python backend,
a Fusion workflow client and a Streamable HTTP MCP server in one application.

The application is called **FusionMCP** in its configuration and deployment files.
The intended GitHub repository name is `oci-eai-fusion-mcp`.

## How it works

```text
Browser -> Python backend -> OCI Responses API -> MCP tool -> Fusion workflow
                    ^                                      |
                    +--------------- result ---------------+
```

The backend and MCP server run in the same process. The Fusion client obtains
and reuses a token, invokes a published workflow asynchronously, and polls for
its result. Additional workflows can be configured in `agents.json`.
The page displays the answer and evidence of the MCP call.

No separate Node.js build or database is required.

## Demo video

An EAI-to-Fusion walkthrough video has been recorded. A link will be added once
it is published. Video files and production assets are kept outside this repository.

## Prerequisites

* Python 3.11 in a named Conda environment, and PowerShell 7.2+ for the supplied scripts.
* An OCI Generative AI project, API key and model that supports remote MCP calls.
* An accessible Fusion environment with a published AI Agent Studio workflow,
  a Fusion username/password and permission to run that workflow.
* A publicly reachable HTTPS MCP endpoint for the full EAI route. OCI cannot
  call an MCP endpoint running only on your laptop.

You supply your own services and credentials. The project does not create a
Fusion workflow or include access to the author's running demonstration.

## Run locally

Open PowerShell in the project folder:

```powershell
# On first setup only; keep your existing .env when updating the code.
Copy-Item .env.example .env
# Fill the placeholders in .env with your own configuration.
.\Setup.ps1
.\Start.ps1
```

`Setup.ps1` creates the named `fusionmcp` environment if needed, installs the
pinned runtime dependencies and checks configuration without making service calls.
The current setup check also requires the deployment/operator placeholders in
`.env.example` to be filled; it does not create or deploy OCI resources.

Open http://localhost:8080 and select **Direct Fusion test** first. This checks
the Fusion connection without an EAI callback. Stop the local server with Ctrl+C.
If needed, enter a temporary Fusion password in the page. It applies only to
that session and is not saved to `.env`.

## Run the full EAI + MCP demo

Host the application on OCI Generative AI Hosted Applications, then use its
hosted browser page and select **EAI + MCP**. The browser derives the MCP callback
URL from its own hosted URL. Both routes must use the same running instance
because session state is in memory.

`Dockerfile` builds the application for Python 3.11. `agent.yaml` describes
the build and deployment configuration for the
[OCI agent deployment helpers](https://github.com/luigisaetta/codex-4-oci-enterprise-ai-deployment).
The manifest is not a standalone OCI CLI command. It reads runtime settings
from your environment; credentials must not be embedded in the image or manifest.

See [TUTORIAL.md](TUTORIAL.md) for configuration, deployment context and adding workflows.

## Local checks

```powershell
# Offline configuration check; reports names/status, never credential values.
conda run --no-capture-output -n fusionmcp python check_config.py

# Offline tests with mocked service calls; no OCI or Fusion requests.
conda run --no-capture-output -n fusionmcp python -m unittest discover -s tests -v
```

The scripts `test_fusion.py`, `test_mcp_live.py` and `test_eai.py` make real
service calls when run explicitly. They are not part of the offline test command.

## Main files

| File | Purpose |
|---|---|
| `fusion.py` | Fusion tokens, asynchronous workflow invocation and bounded polling |
| `catalog.py`, `agents.json` | Configurable workflow/tool catalog |
| `runtime.py` | In-memory sessions and per-session Fusion clients |
| `eai.py` | OCI Responses API calls and MCP-call evidence |
| `server.py` | Browser/API routes and Streamable HTTP MCP at `/mcp` |
| `static/index.html` | Browser demo and architecture diagram |
| `.env.example` | Configuration template with placeholders |
| `Dockerfile`, `agent.yaml` | Container and deployment configuration |

## Demo boundaries

This is demonstration code. The supplied hosted profile is `public-noauth`:
anyone who can reach the page can start a session and use the configured service
connections. The automatic session bearer routes callbacks; it is not user sign-in.
Use a dedicated demo environment and demo data. Production identity and access
control are outside this example.

Use one server process and one replica. Sessions and token caches are in memory
and reset on restart; multiple replicas are not supported by this example.
The model receives an opaque callback bearer, not the Fusion password as a
prompt or tool argument.

## References and acknowledgements

* [OCI Responses API](https://docs.oracle.com/en-us/iaas/Content/generative-ai/responses-api.htm)
* [OCI Enterprise AI quick start](https://docs.oracle.com/en-us/iaas/Content/generative-ai/get-started-agents.htm)
* [OCI Generative AI Hosted Applications](https://docs.oracle.com/en-us/iaas/Content/generative-ai/applications.htm)
* [Luigi Saetta's OCI agent deployment helpers](https://github.com/luigisaetta/codex-4-oci-enterprise-ai-deployment), used for the deployment workflow.

The Fusion connection builds on the author's ODA-to-Fusion integration. That
ODA component is a separate example; this repository contains the EAI/MCP route.

## License

This project is licensed under the [MIT License](LICENSE).
Copyright (c) 2026 M. Dijkens.
