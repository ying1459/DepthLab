# Contributing to Depth Lab

Thank you for helping improve Depth Lab.

## Development setup

1. Install Python 3.10 or newer.
2. Create a virtual environment.
3. Install `requirements.txt` and `requirements-dev.txt`.
4. Run `pytest -q` before opening a pull request.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

The model checkpoint is not needed for the unit tests. For real inference, allow Transformers to download the official Small checkpoint or run `scripts/download_model.ps1`.

## Pull requests

- Keep changes focused and explain the user-visible outcome.
- Add or update tests when behavior changes.
- Do not commit videos, generated job data, virtual environments, builds, release binaries, secrets, or model weights.
- Preserve local-only processing unless a proposal explicitly discusses a different privacy model.
- Confirm that newly introduced dependencies allow redistribution.

By contributing, you agree that your contribution is licensed under the repository's MIT License.
