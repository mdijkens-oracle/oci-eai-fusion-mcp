"""Verify remote MCP request shape and honest tool evidence handling."""
import unittest
from types import SimpleNamespace as Obj
from eai import ask
from fusion import FusionError

class EaiTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_mcp_request(self):
        recorded={}
        async def create(**kwargs):
            recorded.update(kwargs)
            return Obj(output=[Obj(type="mcp_call",name="ask_fusion_agent",status="completed",error=None)],output_text="answer")
        result=await ask(Obj(responses=Obj(create=create)),{"MCP_SERVER_URL":"https://example.com/mcp","GENAI_MODEL":"m"},
                         {"tool":"ask_fusion_agent"},"question","session-only")
        tool=recorded["tools"][0]
        self.assertEqual(tool["authorization"],"session-only")
        self.assertEqual(tool["allowed_tools"],["ask_fusion_agent"])
        self.assertEqual(result["answer"],"answer")
        self.assertFalse(recorded["store"])
        self.assertIn("ask_fusion_agent",recorded["instructions"])
        self.assertIn("ask_fusion_agent",recorded["input"])
        self.assertTrue(recorded["input"].endswith("question"))

    async def test_no_tool_call_is_not_success(self):
        async def create(**kwargs): return Obj(output=[],output_text="invented answer")
        with self.assertRaises(FusionError) as error:
            await ask(Obj(responses=Obj(create=create)),{"MCP_SERVER_URL":"https://example.com/mcp","GENAI_MODEL":"m"},
                      {"tool":"ask_fusion_agent"},"question","session-only")
        self.assertEqual(error.exception.code,"MCP_NOT_COMPLETED")

