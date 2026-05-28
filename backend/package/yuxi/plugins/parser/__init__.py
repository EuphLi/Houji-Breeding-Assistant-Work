from importlib import import_module

__all__ = [
    "BaseDocumentProcessor",
    "DocumentParserException",
    "DocumentProcessorException",
    "OCRException",
    "DocumentProcessorFactory",
    "MarkdownParseResult",
    "Parser",
    "SUPPORTED_FILE_EXTENSIONS",
    "is_supported_file_extension",
    "parse_source_to_markdown",
]


class Parser:
    @classmethod
    async def aparse(cls, source: str, params: dict | None = None) -> str:
        return await import_module("yuxi.plugins.parser.unified").Parser.aparse(source, params)

    @classmethod
    def parse(cls, source: str, params: dict | None = None) -> str:
        return import_module("yuxi.plugins.parser.unified").Parser.parse(source, params)


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
    if name in {
        "MarkdownParseResult",
        "SUPPORTED_FILE_EXTENSIONS",
        "is_supported_file_extension",
        "parse_source_to_markdown",
    }:
        return getattr(import_module("yuxi.plugins.parser.unified"), name)
    raise AttributeError(f"module 'yuxi.plugins.parser' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
