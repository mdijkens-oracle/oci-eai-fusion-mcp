"""Author: M. Dijkens. In-memory demo sessions; no credentials enter tool schemas."""
import asyncio
from dataclasses import dataclass, field
import secrets
import time
from fusion import Connection, FusionClient, FusionError

@dataclass(repr=False)
class Session:
    client: FusionClient
    expires: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

class Sessions:
    def __init__(self, settings):
        self.settings, self.items = settings, {}

    async def create(self, password=None):
        for token, session in list(self.items.items()):
            if session.expires < time.time() and not session.lock.locked():
                await session.client.aclose()
                del self.items[token]
        if len(self.items) >= 32:
            raise FusionError("SESSION_LIMIT", "Too many active sessions. Try again later.")
        c = self.settings
        connection = Connection(c.get("FUSION_BASE_URL",""), c.get("FUSION_USERNAME",""),
                                password if password else c.get("FUSION_PASSWORD",""), c.get("FUSION_SCOPE") or "")
        token = secrets.token_urlsafe(32)
        self.items[token] = Session(FusionClient(connection), time.time()+3600)
        return token

    def get(self, token):
        session = self.items.get(token)
        if not session or session.expires <= time.time(): return None
        return session

    async def close(self):
        for session in self.items.values(): await session.client.aclose()
        self.items.clear()

