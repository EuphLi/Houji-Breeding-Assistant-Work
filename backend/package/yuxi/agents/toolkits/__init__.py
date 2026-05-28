"""
import yuxi.agents.toolkits
↓
toolkits/__init__.py 执行
↓
from . import breeding, buildin
↓
breeding 模块加载
↓
breeding/tools.py 中 @tool 执行
↓
工具进入 _all_tool_instances
"""

# 总结相关的三份文件：
# 1. registry.py
#    负责注册工具。
#    @tool 把普通函数变成 LangChain Tool，并放入 _all_tool_instances。
#
# 2. toolkits/__init__.py
#    负责触发工具模块 import。
#    from . import breeding 会触发育种工具注册。
#
# 3. tool_service.py
#    负责把已注册工具整理成前端可展示的元数据。


# toolkits 包
# 触发各模块的 @tool 装饰器执行，自动注册工具
from importlib import import_module

from . import breeding
from yuxi.utils import logger


def _import_tool_module(module_name: str) -> None:
    """Import a tool module without letting one failure break the whole registry."""
    try:
        import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to import tool module {module_name}: {type(exc).__name__}: {exc}")


# 显式导入内置工具模块，确保其 @tool 装饰器在包初始化时完成注册。
_import_tool_module("yuxi.agents.toolkits.buildin.pubmed")
_import_tool_module("yuxi.agents.toolkits.buildin.tools")

# 工具获取函数  这把 registry 中的核心函数统一暴露到：yuxi.agents.toolkits
from .registry import (
    ToolExtraMetadata,
    get_all_extra_metadata,
    get_all_tool_instances,
    get_extra_metadata,
    tool,
)

# 声明这个包对外导出的名字。
__all__ = [
    "get_extra_metadata",
    "get_all_extra_metadata",
    "get_all_tool_instances",
    "ToolExtraMetadata",
    "tool",
    # 触发各模块的 @tool 装饰器执行，自动注册工具
    "breeding",
    "buildin",
    "get_common_kb_tools",
    "debug",
    "mysql",
]


# 懒加载机制：当外部访问 buildin/debug/mysql/kbs 相关内容时，再动态 import。
def __getattr__(name: str):
    if name == "get_common_kb_tools":
        return import_module("yuxi.agents.toolkits.kbs").get_common_kb_tools
    if name in {"buildin", "debug", "mysql"}:
        return import_module(f"yuxi.agents.toolkits.{name}")
    raise AttributeError(f"module 'yuxi.agents.toolkits' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
