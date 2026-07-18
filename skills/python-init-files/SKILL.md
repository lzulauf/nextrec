---
name: python-init-files
description: 'Keep __init__.py files empty by default. Import directly from defining modules, not via package-level re-exports. Only add convenience exports for public library packages intended for external consumers.'
argument-hint: 'Describe the package or __init__.py you want to review'
user-invocable: true
reusable: true
---

# Python init Files

Use this skill when reviewing or creating `__init__.py` files to keep them empty unless the package is a public-facing library.

## When To Use

- Creating a new Python package
- Reviewing an existing `__init__.py` that has imports inside it
- Deciding whether to add convenience re-exports to an `__init__.py`
- Onboarding a new contributor who asks about import conventions

## Convention

### Default rule: empty init files

`__init__.py` files should be empty. Consumers import directly from the module that defines the symbol:

```python
# Good
from mypackage.models import Facility
from mypackage.api.client import fetch_facilities

# Not
from mypackage import Facility, fetch_facilities
```

This keeps the import graph flat, explicit, and easy to trace. It avoids circular imports, lazy-loading surprises, and makes `grep`-based discovery reliable.

### Exception: public library packages

If a package is explicitly designed as a library for external developers (published on PyPI, consumed by other projects), add curated convenience exports in `__init__.py`:

```python
# mypackage/__init__.py
from mypackage.models import Facility, Reservation
from mypackage.api import fetch_facilities, create_reservation

__all__ = ["Facility", "Reservation", "fetch_facilities", "create_reservation"]
```

Criteria for adding exports:
- The package has external consumers who should not need to know the internal module layout.
- The public API surface is stable and intentional.
- The `__all__` list is maintained explicitly.

### Anti-pattern: passive re-exports for internal convenience

Do not add imports to `__init__.py` just so internal callers can type less. Internal callers should import from the defining module. This includes:

- Re-exporting submodules so `from mypackage import submodule` works
- Re-exporting symbols for test files
- Re-exporting symbols for sibling modules within the same package

## Checklist

- [ ] Is `__init__.py` empty? If yes, done.
- [ ] If non-empty: is this a public library package with external consumers?
- [ ] If yes: are exports curated and documented in `__all__`?
- [ ] If no: move exports back to the defining modules and empty the init file.
