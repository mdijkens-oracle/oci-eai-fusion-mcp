"""Live OCI Responses API key/model check. No MCP success is implied."""
import asyncio
from pathlib import Path
import os
from dotenv import dotenv_values
from openai import APIError
from eai import make_client

async def main():
    settings={**dotenv_values(Path(__file__).with_name(".env"),interpolate=False),**os.environ}
    async with make_client(settings) as client:
        try:
            r=await client.responses.create(model=settings["GENAI_MODEL"],input="Reply with exactly: EAI OK",store=False)
            print("EAI status:",r.status)
            print(r.output_text)
        except APIError as e:
            print("EAI failed: HTTP",getattr(e,"status_code",None),"(provider body hidden)")
            return 1
    return 0
if __name__=="__main__": raise SystemExit(asyncio.run(main()))

