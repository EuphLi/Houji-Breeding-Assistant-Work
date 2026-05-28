from importlib import import_module

__all__ = [
    "BaseDocumentProcessor",
    "DocumentParserException",
    "DocumentProcessorException",
    "OCRException",
    "DocumentProcessorFactory",
]


def __getattr__(name: str):
    if name in {
        "BaseDocumentProcessor",
        "DocumentParserException",
        "DocumentProcessorException",
        "OCRException",
    }:
        return getattr(import_module("yuxi.plugins.parser.base"), name)
    if name == "DocumentProcessorFactory":
        return import_module("yuxi.plugins.parser.factory").DocumentProcessorFactory
    raise AttributeError(f"module 'yuxi.plugins' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
