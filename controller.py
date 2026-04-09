from flask import Flask, jsonify
import docker
import requests
import time

app = Flask(__name__)
OLLAMA_URL = "http://ollama:11434"
OLLAMA_MODEL = "qwen2.5:14b"

# Wan2GP container config — mirrors docker-compose.yaml
WAN2GP_IMAGE = "local-llm-wan2gp"  # built by docker compose
WAN2GP_CONFIG = {
    "name": "wan2gp",
    "ports": {"8190/tcp": 8190},
    "volumes": {
        "/mnt/c/Users/Palantir/Documents/cdev/local-llm/wan2gp/ckpts": {"bind": "/app/ckpts", "mode": "rw"},
        "/mnt/c/Users/Palantir/Documents/cdev/local-llm/wan2gp/config": {"bind": "/app/config", "mode": "rw"},
    },
    "environment": {"CUDA_VISIBLE_DEVICES": "0"},
    "device_requests": [
        docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
    ],
    "detach": True,
    "restart_policy": {"Name": "no"},
    "network": "local-llm_default",
}

client = docker.from_env()


def get_or_create_wan2gp():
    """Return the wan2gp container, creating it if it doesn't exist."""
    try:
        return client.containers.get("wan2gp")
    except docker.errors.NotFound:
        return client.containers.create(WAN2GP_IMAGE, **WAN2GP_CONFIG)


@app.route("/start", methods=["POST"])
def start():
    # Evict Ollama model from VRAM before Wan2GP claims the GPU.
    try:
        requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "keep_alive": 0},
            timeout=10,
        )
        time.sleep(2)
    except Exception:
        pass

    # Start the container. "started" means the container is running —
    # NOT that Wan2GP is ready. function.py polls /health until it is.
    try:
        container = get_or_create_wan2gp()
        if container.status != "running":
            container.start()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "started"})


@app.route("/stop", methods=["POST"])
def stop():
    try:
        container = client.containers.get("wan2gp")
        if container.status == "running":
            container.stop()
    except docker.errors.NotFound:
        pass
    return jsonify({"status": "stopped"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8189)