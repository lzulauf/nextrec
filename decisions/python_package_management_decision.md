Decision title: Python package management and build backend

Problem statement
-----------------
Choose a consistent, modern, and low-friction toolchain for building, dependency management, and virtual environments for this Python project.

Why this matters
-----------------
- Consistency reduces onboarding friction and CI complexity.
- A PEP-compliant setup (pyproject.toml) future-proofs packaging and publishing.
- The choice impacts developer workflows (installing, testing, publishing) and CI tooling.

Goals and decision criteria
--------------------------
- PEP 517/518 / PEP 621 compatibility
- Fast, reliable dependency resolution with a lockfile
- Minimal friction for contributors on Windows and CI
- Clear publishing story (build -> wheel/sdist)
- Good support for editable installs during development

Options considered
------------------
1) Hatch/hatchling + PDM
2) Poetry (poetry + poetry-core)
3) Setuptools (setuptools + wheel) + pip + pip-tools
4) UV as dependency manager + standard PEP build backend
5) UV Build as packaging/build command wrapper

Tradeoff analysis
-----------------
Option 1 — Hatch/hatchling + PDM
- What this means: Use `hatchling` as the build backend declared in `pyproject.toml`, and `pdm` as the developer-facing dependency manager. Rely on PDM's venv support or use `python -m venv`.
- Pros: Modern, lightweight, strict PEP compliance, fast resolver, good editable-install support, minimal magic. `hatch` provides useful versioning and environment management helpers.
- Cons: Slightly smaller ecosystem than Poetry; contributors unfamiliar with PDM may need a short onboarding note.

Option 2 — Poetry
- What this means: Use `poetry` for dependency management and `poetry-core` as the build backend.
- Pros: Widely adopted, excellent UX, single tool for deps, publishing, and scripts. Strong community and documentation.
- Cons: Historically heavier and opinionated; earlier versions had issues with editable installs (improved in modern Poetry), and some CI flows need explicit steps to use the lockfile.

Option 3 — Setuptools + pip + pip-tools
- What this means: Classic setup with `setuptools` for builds, `pip` for installs, and `pip-tools`/constraints for lockfile-style reproducibility.
- Pros: Very stable and familiar to most Python developers; maximum compatibility.
- Cons: More manual work to maintain `requirements.txt`/lock constraints; not as PEP-modern (pyproject support exists but tends to be more manual).

Option 4 — UV as dependency manager + standard PEP build backend
- What this means: Use `uv` for dependency resolution, lockfile creation, and environment management, while declaring a standard PEP 517/518 build backend in `pyproject.toml`.
- Pros: Minimal footprint, fast dependency resolution, and a small CLI surface. It is a lightweight alternative to Poetry and PDM and can work with any compliant build backend.
- Cons: Less common than Poetry/PDM, smaller ecosystem, and may require documentation for contributors unfamiliar with `uv`. It still requires a separate build backend for artifact creation.

Option 5 — UV Build as packaging/build command wrapper
- What this means: Use `uv_build` to provide a thin wrapper for build and packaging commands around a PEP build backend declared in `pyproject.toml`.
- Pros: Can simplify commands for projects already using `uv`, while still keeping standard pyproject build metadata.
- Cons: Not a standalone build backend; it adds another tool and can be unnecessary unless the team decides to adopt `uv` broadly.

Valid combinations and assumptions
----------------------------------
- `pyproject.toml` is the source of truth for build backend configuration.
- A build backend can be `hatchling`, `setuptools`, `poetry-core`, or another PEP 517-compatible backend.
- Dependency managers are distinct from build backends except in cases like Poetry where the same tool provides both.
- `Hatchling + PDM` is valid and common: PDM manages deps, hatchling builds artifacts.
- `Poetry` is valid as an integrated toolchain: Poetry manages deps and uses `poetry-core` as the build backend.
- `Setuptools + pip + pip-tools` is valid for a more traditional workflow with explicit requirements/lockfile maintenance.
- `UV` is valid as a dependency manager paired with any standard build backend; it does not replace the backend itself.
- `UV Build` is valid as a build-wrapper/command helper, but it still assumes a declared PEP build backend in `pyproject.toml`.


Recommendation
--------------
Primary recommendation (modern, low-friction):
- Build backend: `hatchling` (declare in `pyproject.toml` under `build-system`)
- Dependency manager: `pdm` (use `pdm.lock` for reproducible installs)
- Virtual env strategy: Use `pdm`'s venv management for local development, and CI should create a clean venv with the target Python and run `pdm install --no-edit` for reproducible installs. Recommend documenting `python` version via `pyproject.toml` `requires-python` and optionally using `pyenv`/`pyenv-win` for pinned interpreter management.

Rationale
---------
- `hatchling` + `pdm` is fully PEP-compliant, fast, and minimal — good for both contributors and CI on Windows.
- PDM provides modern dependency resolution and first-class pyproject support while avoiding the heavier runtime tooling that Poetry historically introduced.
- This stack supports editable installs, clear lockfiles, and easy publishing via `hatch build` when we need to produce wheels/sdists.

Fallback / alternative
----------------------
- If the team prefers a single-tool UX and wider community familiarity, adopt `poetry` (with `poetry-core` as the build backend). It covers dependency resolution, publishing, and dev scripts in one surface.

Migration notes / quick start snippets
-----------------------------------
- Minimal `pyproject.toml` `build-system` snippet for hatchling:

  [build-system]
  requires = ["hatchling>=1.0"]
  build-backend = "hatchling.build"

- Suggested developer quickstart (Windows / CI):

  - Install PDM: `python -m pip install --user pdm`
  - Create project venv: `pdm venv create` or let `pdm install` create one automatically
  - Install dependencies: `pdm install --dev`
  - Build distributions: `pdm run hatch build` or `python -m build` if using the `build` package

Follow-up actions
-----------------
- Add a short `CONTRIBUTING.md` section with the chosen commands and how to install `pdm` on Windows.
- Add `pyproject.toml` scaffold to the repo and update CI to use the recommended install flow.

Confidence and risks
--------------------
- Confidence: Medium-High. The `hatch`/`pdm` combination is stable and PEP-aligned, but requires a short onboarding note for contributors who are used to `pip`/`venv` or `poetry`.
- Risk: Minimal; alternative (`poetry`) is a straightforward swap if team preference dictates.
