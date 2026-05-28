from importlib import import_module

__all__ = [
    "ask_user_question",
    "calculator",
    "present_artifacts",
    "query_knowledge_graph",
    "text_to_img_qwen_image",
    "pubmed_search",
]


def __getattr__(name: str):
    if name == "pubmed_search":
        return getattr(import_module("yuxi.agents.toolkits.buildin.pubmed"), name)
    if name in {
        "ask_user_question",
        "calculator",
        "present_artifacts",
        "query_knowledge_graph",
        "text_to_img_qwen_image",
    }:
        return getattr(import_module("yuxi.agents.toolkits.buildin.tools"), name)
    raise AttributeError(f"module 'yuxi.agents.toolkits.buildin' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
