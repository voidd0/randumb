from pathlib import Path


def main() -> int:
    Path("/app/storage").mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
