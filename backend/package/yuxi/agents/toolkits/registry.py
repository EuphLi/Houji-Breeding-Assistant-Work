from collections.abc import Callable
from dataclasses import dataclass, field

"""
当前完整的工具链路：

后端Agent执行链路：
breeding/tools.py 中的函数
↓
@tool 装饰器
↓
toolkits/registry.py
    _all_tool_instances
    _extra_registry
↓
toolkits/__init__.py
    import breeding 触发注册
↓
RuntimeConfigMiddleware
    get_all_tool_instances()
    根据 context.tools 筛选工具
↓
LangChain create_agent
↓
模型可见工具

前端配置链路：
breeding/tools.py
↓
@tool
↓
registry._extra_registry + _all_tool_instances
↓
tool_service.get_tool_metadata()
↓
/system/tools
↓
前端工具选择页面
↓
AgentConfig.config_json.context.tools
↓
执行时进入 BaseContext.tools
 
*** 这两条线最后在 context.tools 汇合 ***

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


# 这个文件在链路中的作用：
# 1. 提供 `@tool` 装饰器，把普通函数注册成 YuXi 可调用工具；
# 2. 记录工具的显示名称、分类、标签等扩展管理信息；
# 3. 维护“当前系统里有哪些工具可被 Agent 调用”的全局集合。
#
# 可以把它理解为“Tool 注册中心”。
# YuXi 自带的是这套通用注册机制；育种 Tool 是在这套机制上新增的业务工具。


@dataclass
class ToolExtraMetadata:
    """附加元数据（用装饰器注册）"""

    category: str = ""  # 分类: buildin, mysql, subagents, debug
    tags: list[str] = field(default_factory=list)  # 每创建一个 ToolExtraMetadata 对象，都新建一个空 list。
    display_name: str = ""  # 显示名称（给人看的名字）
    icon: str = ""  # 图标
    config_guide: str = ""  # 配置说明（给人看的使用前配置提示）


# 全局注册表: tool_name -> ToolExtraMetadata
# 全局字典 根据工具名称 tool_name，找到这个工具的附加信息。
_extra_registry: dict[str, ToolExtraMetadata] = {}

# 全局工具实例列表（由 @tool 装饰器自动收集）
# 全局列表 保存所有已经注册的 Tool 实例（LangChain Tool 对象）
# 这才是后续 RuntimeConfigMiddleware 真正会读取的工具集合
_all_tool_instances: list = []

# 输入工具名 tool_name；去 _extra_registry 里面查；如果查到，返回 ToolExtraMetadata；查不到，返回 None。
def get_extra_metadata(tool_name: str) -> ToolExtraMetadata | None:
    """获取工具附加元数据"""
    return _extra_registry.get(tool_name)  # .get()，key不存在时可以返回None


def get_all_extra_metadata() -> dict[str, ToolExtraMetadata]:
    """获取所有附加元数据"""
    return _extra_registry.copy()  # .copy() 是保护原始全局注册表


# 告诉系统：当前有哪些工具可以用。只是返回工具列表，不执行工具
def get_all_tool_instances() -> list:
    """获取所有工具实例（由 @tool 装饰器自动收集）

    前端扩展管理、测试里的 Tool 注册检查，以及 Agent 可调用工具列表都依赖这里。
    这个函数只返回“系统里注册了哪些 Tool”，不执行任何育种逻辑。
    它被 RuntimeConfigMiddleware 使用，是 Tool Registry → Agent 工具绑定机制 之间的桥梁
    """
    return _all_tool_instances


# 基于 langchain.tool 的拓展装饰器
def tool(
    category: str = "",
    tags: list[str] = None,
    display_name: str = "",
    icon: str = "",
    config_guide: str = "",
    name_or_callable: str | Callable | None = None,
    description: str | None = None,
    args_schema: type | None = None,
    return_direct: bool = False,
):
    """基于 langchain.tool 的拓展装饰器，同时注册元数据

    使用方式:
    @tool(category="buildin", tags=["计算"], display_name="计算器")
    def calculator(a: float, b: float, operation: str) -> float:
        ...

    或者保留原有的 name_or_callable 和 description:
    @tool(
        category="buildin",
        display_name="查询知识图谱",
        name_or_callable="查询知识图谱",
        description=KG_QUERY_DESCRIPTION,
    )
    def query_knowledge_graph(query: str) -> str:
        ...
    """
    from langchain.tools import tool as langchain_tool

    # 这里是 YuXi 通用 Tool 机制的入口：
    # - 先把函数包装成 LangChain Tool
    # - 再把显示信息和实例登记到全局注册表
    #
    # 真正的业务逻辑仍然写在各个 Tool 函数内部，例如 breeding/tools.py。
    # 先应用 langchain tool 装饰器
    langchain_decorator = langchain_tool(
        name_or_callable=name_or_callable,
        description=description,
        args_schema=args_schema,
        return_direct=return_direct,
    )

    def decorator(func: Callable) -> Callable:
        # 应用 langchain 装饰器
        tool_obj = langchain_decorator(func)

        # 注册附加元数据
        tool_name = tool_obj.name
        _extra_registry[tool_name] = ToolExtraMetadata(
            category=category,
            tags=tags or [],
            display_name=display_name,
            icon=icon,
            config_guide=config_guide,
        )

        # 自动收集工具实例
        _all_tool_instances.append(tool_obj)

        return tool_obj

    return decorator
