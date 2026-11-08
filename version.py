"""Single source of truth for the project version.

``README.md`` declares ``Version: 1.0.0`` and H6 (``healers/decl_impl.py``)
treats that declaration as authoritative: it rewrites ``__version__`` in any
Python module that drifts from it. ``pyproject.toml`` reads the value from
here through ``tool.setuptools.dynamic.version``, so packaging has no second
copy of the number that could fall out of sync.
"""

__version__ = "1.0.0"
