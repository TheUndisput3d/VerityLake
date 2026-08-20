import os
import time

import httpx


def wait(url):
    for attempt in range(90):
        try:
            with httpx.Client(timeout=5, trust_env=False) as client:
                client.get(url).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(2)
    raise RuntimeError("Dependency did not become ready")


def main():
    base = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
    wait(base + "/api/tags")
    wait(os.environ.get("CHROMA_BASE_URL", "http://chroma:8000") + "/api/v2/heartbeat")
    with httpx.Client(base_url=base, timeout=1800, trust_env=False) as client:
        for model in (os.environ["EMBEDDING_MODEL"], os.environ["LLM_MODEL"]):
            print("Ensuring local model is installed:", model, flush=True)
            response = client.post("/api/pull", json={"model": model, "stream": False})
            response.raise_for_status()
            if response.json().get("error"):
                raise RuntimeError("Model pull failed")
        response = client.post("/api/embed", json={"model": os.environ["EMBEDDING_MODEL"],
                              "input": "search_document: warmup", "truncate": False})
        response.raise_for_status()
    print("Models downloaded and encoder warmed. Network is still needed for runtime scraping.")


if __name__ == "__main__":
    main()
