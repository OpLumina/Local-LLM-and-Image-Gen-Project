import asyncio
import base64
import time
import requests
from pydantic import BaseModel, Field
from typing import Optional

class Pipe:
    class Valves(BaseModel):
        wan2gp_url: str = Field(default="http://10.0.0.147:8190")
        controller_url: str = Field(default="http://10.0.0.147:8189")
        width: int = Field(default=1024)
        height: int = Field(default=1024)
        steps: int = Field(default=4)
        cfg: float = Field(default=1.0)
        startup_timeout: int = Field(default=600)

    def __init__(self):
        self.type = "pipe"
        self.id = "wan2gp_flux_klein"
        self.name = "Flux Klein 4B Generator"
        self.valves = self.Valves()
        self._running = False  # 🔒 Prevent duplicate execution

    def _is_wan2gp_ready(self) -> bool:
        try:
            r = requests.get(f"{self.valves.wan2gp_url}/health", timeout=2)
            if r.status_code == 200:
                return r.json().get("ready", False)
            return False
        except:
            return False

    def _start_wan2gp(self):
        try:
            requests.post(f"{self.valves.controller_url}/start", timeout=5)
        except:
            pass

    def _wait_for_wan2gp(self) -> bool:
        start_time = time.time()
        while time.time() - start_time < self.valves.startup_timeout:
            if self._is_wan2gp_ready():
                return True
            time.sleep(2)
        return False

    def _generate(self, prompt: str) -> Optional[str]:
        payload = {
            "prompt": prompt,
            "width": self.valves.width,
            "height": self.valves.height,
            "steps": self.valves.steps,
            "cfg": self.valves.cfg
        }
        try:
            r = requests.post(
                f"{self.valves.wan2gp_url}/generate",
                json=payload,
                timeout=300
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("image_b64")
            else:
                print(f"Generation failed: HTTP {r.status_code} - {r.text}")
        except Exception as e:
            print(f"Generation error: {e}")
        return None

    async def pipe(self, body: dict, __event_emitter__=None) -> str:
        # 🔒 HARD GUARD: ensure only one execution at a time
        if self._running:
            return "Already generating. Please wait."

        self._running = True

        try:
            prompt = body.get("messages", [])[-1].get("content", "").strip()

            async def emit(description: str, done: bool = False):
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": description, "done": done}
                    })

            # 1. Check readiness
            already_ready = await asyncio.to_thread(self._is_wan2gp_ready)

            if already_ready:
                await emit("Wan2GP already running, skipping start...")
            else:
                await emit("Starting Wan2GP (unloading Ollama from VRAM)...")
                await asyncio.to_thread(self._start_wan2gp)

                await emit(f"Waiting for Wan2GP to be ready (up to {self.valves.startup_timeout}s)...")
                if not await asyncio.to_thread(self._wait_for_wan2gp):
                    await emit("Timeout: GPU failed to initialize.", done=True)
                    return "Error: Image generation server timed out."

            await emit("Generating image with Flux Klein 4B...")

            # 2. Generate (ONLY ONCE)
            img_b64 = await asyncio.to_thread(lambda: self._generate(prompt))

            if img_b64:
                await emit("Image generated successfully.", done=True)

                # ✅ SINGLE RESPONSE PATH (no duplicate emitter message)
                return f"![Generated Image](data:image/png;base64,{img_b64})"
            else:
                await emit("Generation failed.", done=True)
                return "Failed to generate image. Check server logs."

        finally:
            # 🔓 Always release guard
            self._running = False