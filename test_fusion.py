"""
Author: M. Dijkens
Date last modified: 2026-10-22
License: MIT
Description: Explicit live smoke test of the configured Fusion workflow.
"""
import argparse
import asyncio
import getpass
import os
from pathlib import Path
import sys

from dotenv import dotenv_values
from fusion import Connection, FusionClient, FusionError


async def run(args):
    """Invoke only when explicitly launched; never print credentials or tokens."""
    settings = {**dotenv_values(Path(__file__).with_name(".env"), interpolate=False),
                **os.environ}
    password = getpass.getpass("Fusion password (not saved): ") if args.prompt_password else None
    connection = Connection.from_env(password_override=password)
    workflow = args.workflow or settings.get("FUSION_WORKFLOW")
    async with FusionClient(connection) as client:
        for index in range(args.repeat):
            result = await client.call_agent(workflow, args.message)
            for _ in range(3):
                if result["status"] == "COMPLETE":
                    break
                result = await client.call_agent(
                    workflow, job_id=result["jobId"],
                    conversation_id=result["conversationId"])
            print(f"Run {index + 1}: {result['status']}")
            if result["status"] != "COMPLETE":
                print("The job remains pending; do not resubmit blindly.")
                return 2
            print(result["output"] or "(empty output)")
        print(f"Token acquisitions: {client.token_requests}; completed calls: {args.repeat}")
    return 0


def main():
    """Parse an intentional live test request."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow")
    parser.add_argument("--message", default="Antwoord uitsluitend met: TEST OK")
    parser.add_argument("--repeat", type=int, choices=(1, 2), default=1)
    parser.add_argument("--prompt-password", action="store_true")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except FusionError as error:
        print(f"FAILED: stage={error.stage}; code={error.code}; HTTP={error.http_status}")
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

