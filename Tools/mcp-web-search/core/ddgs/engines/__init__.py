"""Automatically discover enabled web-search engines."""

import importlib
import inspect
import pkgutil
from typing import Any

from ..base import BaseSearchEngine

ENGINES: dict[str, dict[str, type[BaseSearchEngine[Any]]]] = {"text": {}}

package = importlib.import_module(__name__)
for _finder, module_name, _is_package in pkgutil.iter_modules(package.__path__, __name__ + "."):
    module = importlib.import_module(module_name)
    for _, engine_class in inspect.getmembers(module, inspect.isclass):
        if not issubclass(engine_class, BaseSearchEngine) or engine_class is BaseSearchEngine:
            continue
        if engine_class.__name__.startswith("Base") or getattr(engine_class, "disabled", True):
            continue

        name = getattr(engine_class, "name", None)
        category = getattr(engine_class, "category", None)
        if not isinstance(name, str) or category != "text":
            msg = f"{engine_class.__qualname__} must define name and use the text category."
            raise TypeError(msg)
        ENGINES["text"][name] = engine_class
