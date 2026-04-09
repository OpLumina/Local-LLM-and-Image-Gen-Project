## Local LLM + Image Generation Stack — Context Document

## Machine Info
- **Host**: Windows 11 + WSL2 (`DESKTOP-VOT3EHI`)
- **GPU**: NVIDIA RTX 5060 Ti 16GB (Blackwell, `sm_120`, requires CUDA 12.8+)
- **IP**: `<main-ip>`
- **Project directory**: `/mnt/c/Users/Palantir/Documents/cdev/local-llm/`
- **Open WebUI**: Running on a **separate machine** on the LAN at `<open-webui-ip>:8080`

---

## Stack Overview

| Service | Image | Port | Purpose |
|---|---|---|---|
| `ollama` | `ollama/ollama:latest` | `11434` | LLM inference (Qwen 2.5 14B) |
| `wan2gp` | `local-llm-wan2gp` | `8190` | Flux Klein 4B image generation |
| `wan2gp-controller` | `local-llm-wan2gp-controller` | `8189` | Remote orchestration (Start/Stop Docker) |

---

## Deployment Status & Key Accomplishments

### 1. Wan2GP Integration (Flux Klein 4B)
- **Automatic Dependencies**: Successfully handled the initial ~15GB download of auxiliary models (FFmpeg, Wav2Vec, Depth Anything V2, SAM, and Qwen3 Text Encoder).
- **Weight Alignment**: Resolved `[SKIP]` errors by aligning filenames to underscores (e.g., `flux2_klein_4b.safetensors`).
- **Quantization**: The system successfully transitioned to the `quanto_bf16_int8` stack, allowing for high-speed inference on 16GB VRAM.

### 2. Video-to-Image Pipeline
- **Observation**: Wan2GP treats the Flux Klein architecture as a video model, defaulting to `.mp4` output.
- **Solution**: Implemented a frame extraction bridge in `wan2gp_server.py`.
- **Logic**: The server now detects `.mp4` files, uses the local `./ffmpeg` binary to extract the first frame as a `.png`, and serves that to Open WebUI as a Base64 string.

### 3. VRAM Orchestration
- **Controller Logic**: Created a Python controller to manage the handoff between Ollama and Wan2GP.
- **Safety**: Wan2GP only runs when requested. The controller ensures Ollama is "evicted" (keep_alive=0) before Wan2GP claims the GPU to prevent OOM errors on the 16GB hardware.

---

## Known Issues & Log Signatures

| Log Message | Status | Explanation |
|---|---|---|
| `[GGUF] kernels unavailable, using fallback` | **Normal** | Expected on RTX 50 series (Blackwell) due to new architecture; GPU acceleration still functions. |
| `POST /generate ... 500` (after 200) | **Monitoring** | Caused by Open WebUI retry logic. The first request (200) is usually the valid one. |
| `Unreadable image` | **Resolved** | Fixed by adding a 1s write-delay and verifying file size before Base64 encoding. |

---

## Technical Maintenance Commands

### Restart Service
```bash
docker compose restart wan2gp
```

### Check Generated Files (Inside Container)
```bash
docker exec wan2gp ls -lh /app/outputs/
```

### Monitor Blackwell GPU Performance
```bash
nvidia-smi -l 1
```

---

## Todo / Next Steps
- [ ] **Timeout Adjustment**: Ensure Open WebUI Function Valves are set to `900s` for the initial model load.
- [ ] **Disk Management**: Periodically verify that the `/app/outputs/` directory is being purged correctly by the server logic.
- [ ] **Performance Tuning**: Once stable, experiment with reducing `steps` from 4 to 1–2 to see if Flux Klein quality holds for faster generation.
