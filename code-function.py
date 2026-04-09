import asyncio
import json
import requests
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        ollama_url: str = Field(default="http://10.0.0.147:11434")
        ollama_model: str = Field(default="qwen2.5:14b")
        wan2gp_url: str = Field(default="http://10.0.0.147:8190")
        controller_url: str = Field(default="http://10.0.0.147:8189")

    def __init__(self):
        self.type = "pipe"
        self.id = "ollama_qwen"
        self.name = "Qwen 2.5 14B"
        self.valves = self.Valves()

    def _is_wan2gp_running(self) -> bool:
        try:
            r = requests.get(f"{self.valves.wan2gp_url}/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def _stop_wan2gp(self):
        try:
            requests.post(f"{self.valves.controller_url}/stop", timeout=30)
        except Exception:
            pass

    async def pipe(self, body: dict, __user__: dict = None, __event_emitter__=None) -> str:
        messages = body.get("messages", [])

        async def emit(msg, done=False):
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": msg, "done": done}})

        # Stop Wan2GP if running so Ollama can claim full VRAM
        if await asyncio.to_thread(self._is_wan2gp_running):
            await emit("Stopping Wan2GP to free VRAM for Ollama...")
            await asyncio.to_thread(self._stop_wan2gp)

        try:
            def stream_ollama():
                return requests.post(
                    f"{self.valves.ollama_url}/api/chat",
                    json={
                        "model": self.valves.ollama_model,
                        "messages": messages,
                        "stream": True,
                    },
                    stream=True,
                    timeout=120,
                )

            r = await asyncio.to_thread(stream_ollama)
            r.raise_for_status()

            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token and __event_emitter__:
                    await __event_emitter__({"type": "message", "data": {"content": token}})
                if chunk.get("done"):
                    break

        except Exception as e:
            return f"Error calling Ollama: {str(e)}"

        return ""