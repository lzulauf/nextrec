# Contributing

Quick developer setup (recommended: `pdm`)

1. Install PDM (single-user):

```bash
python -m pip install --user pdm
```

2. Create a project venv and install dependencies:

```bash
pdm install --dev
```

3. Install Playwright browsers:

```bash
pdm run playwright install
```

Run the discovery capture (headed) to perform manual login and capture session state:

```bash
pdm run python scripts/capture_oakland_discovery.py --url "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List" --out docs/discovery --headed
```

Fallback (if you prefer pip/requirements.txt):

```bash
python -m pip install -r requirements.txt
playwright install
```

Notes
- We recommend PDM + hatchling (see `pyproject.toml`) for a PEP-compliant workflow. If you are unfamiliar with PDM, the fallback pip path will still work for development.
