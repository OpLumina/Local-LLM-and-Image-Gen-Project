import base64
import os
import sys
import threading
import time
from pathlib import Path
from flask import Flask, jsonify, request

app = Flask(__name__)

WAN2GP_ROOT = Path("/app")
OUTPUT_DIR = WAN2GP_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Global session — initialized once on first request
_session = None
_session_lock = threading.Lock()
_generation_lock = threading.Lock() # Prevents duplicate requests from crashing GPU
_session_ready = False

def get_session():
    global _session, _session_ready
    with _session_lock:
        if _session is None:
            sys.path.insert(0, str(WAN2GP_ROOT))
            from shared import api as wan_api
            _session = wan_api.init(
                root=WAN2GP_ROOT,
                cli_args=[
                    "--profile", "4",       
                    "--attention", "sdpa",  
                ],
                console_output=True,
            )
            _session_ready = True
        return _session

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "ready": _session_ready})

@app.route("/generate", methods=["POST"])
def generate():
    if not _generation_lock.acquire(blocking=False):
        # Tell the UI to back off, we are still working
        return jsonify({"status": "error", "message": "GPU is busy"}), 429

    try:
        data = request.json
        prompt = data.get("prompt", "a cat")
        
        session = get_session()
        task = {
            "model_type": "flux2_klein_4b",
            "prompt": prompt,
            "width": int(data.get("width", 1024)),
            "height": int(data.get("height", 1024)),
            "num_inference_steps": int(data.get("steps", 4)),
            "guidance_scale": float(data.get("cfg", 1.0)),
            "image_count": 1,
            "output_dir": str(OUTPUT_DIR),
            "frame_count": 1,
            "save_as_video": False,
        }

        job = session.submit_task(task)
        result = job.result(timeout=300)

        if not result.success or not result.generated_files:
            raise Exception(f"Generation failed: {result.errors if hasattr(result, 'errors') else 'Unknown error'}")

        raw_path = result.generated_files[0]
        img_path = raw_path

        if raw_path.endswith(".mp4"):
            frame_path = raw_path.replace(".mp4", ".png")
            os.system(f'ffmpeg -i "{raw_path}" -frames:v 1 "{frame_path}" -y')
            time.sleep(1.5) 
            img_path = frame_path

        with open(img_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')

        # Cleanup
        try:
            if os.path.exists(raw_path): os.remove(raw_path)
            if img_path != raw_path and os.path.exists(img_path): os.remove(img_path)
        except: pass

        # SUCCESSFUL RETURN
        return jsonify({"status": "ok", "image_b64": img_b64})

    except Exception as e:
        print(f"!!! SERVER ERROR: {str(e)}") # This will show in your docker logs
        return jsonify({"status": "error", "message": str(e)}), 500
    
    finally:
        # COOLDOWN: Wait 2 seconds before letting another request in.
        # This stops the "Double Request" from hitting the GPU while it's still clearing VRAM.
        time.sleep(2)
        _generation_lock.release()

if __name__ == "__main__":
    # Pre-warm the model in a background thread
    threading.Thread(target=get_session, daemon=True).start()
    app.run(host="0.0.0.0", port=8190, threaded=True)