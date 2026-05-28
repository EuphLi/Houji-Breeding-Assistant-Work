from importlib import import_module

__all__ = [
    # Base classes
    "BaseAgent",
    "BaseContext",
    "BaseState",
    # Model utilities
    "load_chat_model",
    # Core tools
    "get_tool_info",
    # Core MCP
    "get_enabled_mcp_tools",
]


def __getattr__(name: str):
    if name == "BaseAgent":
        return import_module("yuxi.agents.base").BaseAgent
    if name == "BaseContext":
        return import_module("yuxi.agents.context").BaseContext
    if name == "BaseState":
        return import_module("yuxi.agents.state").BaseState
    if name == "load_chat_model":
        return import_module("yuxi.agents.models").load_chat_model
    if name == "get_tool_info":
        return import_module("yuxi.agents.toolkits.utils").get_tool_info
    if name == "get_enabled_mcp_tools":
        return import_module("yuxi.services.mcp_service").get_enabled_mcp_tools
    raise AttributeError(f"module 'yuxi.agents' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
