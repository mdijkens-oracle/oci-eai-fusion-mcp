# FusionMCP: small, reusable demo

## 1. Supply your own configuration

Copy .env.example to .env. Use your existing working OCI Generative AI API key,
project, region and supported model. Fill the Fusion origin, username, current
password and published workflow code. No OAuth client registration is involved.

The proven Fusion token request uses Basic authentication against
/crmRestApi/resources/latest/actionplans/action/getProcessAccessToken,
Override-Scope and application/vnd.oracle.adf.action+json. The component derives
the scope for supported Fusion hostnames; FUSION_SCOPE overrides derivation.
The token itself is internal and is not an input to the demo.

The Fusion user must already have permission to run the selected published
workflow. This wrapper does not grant Fusion roles or create workflows.

## 2. Run the local example

Run Setup.ps1, then Start.ps1. Use the direct Fusion test first. The client
requests a token once and reuses it until near expiry; a 401 causes one renewal.
Repeated calls within a browser session reuse the same client/token cache.
Separate browser sessions deliberately have separate clients.

A pending Fusion job can be resumed through the MCP tool using job_id, without
submitting the question again. Tool output contains status, output, jobId,
conversationId and workflow. Polling is bounded.

## 3. Add another Fusion agent

Add a second entry to agents.json:

```json
{
  "tool": "ask_hcm_agent",
  "title": "HCM demo agent",
  "workflow_env": "FUSION_HCM_WORKFLOW",
  "description": "Ask the published HCM demo workflow a question. Resume a pending job using job_id."
}
```

Add FUSION_HCM_WORKFLOW to the private .env and restart/rebuild the app.
Use a precise description so EAI knows what the tool can do.
For example, a leave-balance agent still needs an existing published HCM workflow
and the relevant Fusion permissions/data. No leave-balance endpoint is invented.
To share this setting, add its placeholder to .env.example. For hosting, add
its from_env entry to agent.yaml.

All catalog entries share the same configured Fusion connection. Per-user or
per-environment connection catalogs are intentionally outside this tiny example.

## 4. Host the complete demo

The target is OCI Generative AI Hosted Applications: one Linux/amd64 container,
port 8080, managed networking. The platform profile is public-noauth; the app
automatically creates anonymous sessions and uses an opaque bearer for MCP callback routing.
Keep a single worker/replica because session data is in memory.

The model sees the MCP tool schema and question. It receives an opaque session
credential for the callback; it never receives the Fusion password as a prompt
or tool argument. No demo access key is required.

Build and verify the image, publish it to your private OCIR repository, then
create the hosted application using agent.yaml. The private .env supplies
from_env runtime settings; do not embed these values in the image/manifest.
The browser derives the hosted MCP callback URL from its own application URL.
No second deployment is required.

If the weekly Fusion password changes, enter it in the page under Fusion password (optional).
That override applies to one session and does not rewrite .env or the hosted
application configuration. Click Use password to apply it to a new automatic session.

## 5. Demonstrate

Open the hosted page, optionally enter the new weekly
Fusion password, select EAI + MCP, and ask a question.
Expand "See the call path" to show actual MCP events and token acquisition count.
The app reports an error if EAI did not make a successful MCP call; a plain model
answer is never presented as proof that Fusion ran.

## 6. Share the example

Share the repository URL once published. Each reader supplies their own named
Conda environment fusionmcp, private .env, OCI resources and published Fusion
workflow. Keep local settings, release records and video assets out of Git.

The EAI walkthrough video will be linked from README.md once published.
The ODA-to-Fusion walkthrough belongs to the separate ODA integration example.

## References

* OCI Responses API: https://docs.oracle.com/en-us/iaas/Content/generative-ai/responses-api.htm
* Remote MCP quick start: https://docs.oracle.com/en-us/iaas/Content/generative-ai/get-started-agents.htm
* Hosted Applications: https://docs.oracle.com/en-us/iaas/Content/generative-ai/applications.htm

This is presales demoware, not a production deployment guide.

