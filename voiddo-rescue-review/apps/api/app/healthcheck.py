import json
import sys
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return 0 if payload.get("ok") else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
