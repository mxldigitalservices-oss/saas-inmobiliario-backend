import pkgutil
import importlib
import inspect
from beanie import Document
import app.models

ALL_DOCUMENT_MODELS = []

for _, module_name, _ in pkgutil.iter_modules(app.models.__path__):
    if module_name in ["__init__", "base"]:
        continue
    module = importlib.import_module(f"app.models.{module_name}")
    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)
        if (
            inspect.isclass(attribute)
            and issubclass(attribute, Document)
            and attribute is not Document
        ):
            if attribute not in ALL_DOCUMENT_MODELS:
                ALL_DOCUMENT_MODELS.append(attribute)
