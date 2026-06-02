# Project Instructions

## Testing

- This project is Docker-first. Use the Compose tester service as the primary test command:

  ```bash
  docker compose run --rm tester
  ```

- Do not start by running system-level `pytest`, `python -m pytest`, or `python3 -m pytest` for this repository.
- Only use local pytest as a fallback when Docker is unavailable or the user explicitly asks for local testing.
- If local pytest is used, run it from the repository root with:

  ```bash
  PYTHONPATH=. pytest -q
  ```

- If local pytest fails because dependencies such as `fastapi`, `pydantic`, or `clickhouse-connect` are missing, report that the local Python environment lacks project dependencies. Do not describe this as pytest being unavailable.
