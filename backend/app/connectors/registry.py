"""Connector auto-discovery.

Every module in this package is imported, and every concrete `JobConnector` subclass is
registered by its `source`. A contributor adds a file; nothing else changes.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from sqlalchemy.orm import Session

from app import connectors as connectors_pkg
from app.connectors.base import JobConnector
from app.services import settings_store

_CACHE: dict[str, type[JobConnector]] | None = None


def discover() -> dict[str, type[JobConnector]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    found: dict[str, type[JobConnector]] = {}
    for module_info in pkgutil.iter_modules(connectors_pkg.__path__):
        if module_info.name in ("base", "registry"):
            continue
        module = importlib.import_module(f"{connectors_pkg.__name__}.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, JobConnector)
                and obj is not JobConnector
                and not inspect.isabstract(obj)
                and obj.source
            ):
                found[obj.source] = obj

    _CACHE = found
    return found


def available_sources() -> list[str]:
    return sorted(discover().keys())


def source_labels() -> dict[str, str]:
    return {src: cls.label or src for src, cls in discover().items()}


def build_enabled(db: Session) -> list[JobConnector]:
    """Instantiate the connectors the user has switched on.

    Construction is per-source because some connectors need configuration (Greenhouse
    needs a company list). Defaulting to "all discovered sources" means a fresh install
    searches everything without the user touching Settings first.
    """
    classes = discover()
    enabled = settings_store.get_list(
        db, settings_store.KEY_ENABLED_SOURCES, available_sources()
    )

    instances: list[JobConnector] = []
    for source in enabled:
        cls = classes.get(source)
        if cls is None:
            continue
        if source == "greenhouse":
            instances.append(cls(companies=settings_store.greenhouse_companies(db)))
        else:
            instances.append(cls())
    return instances
