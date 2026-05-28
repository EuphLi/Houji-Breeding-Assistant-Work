from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import AgentConfig
from yuxi.utils.datetime_utils import utc_now_naive

"""
Agent 配置持久化层。负责把与 Agent 相关的配置信息保存到数据库，并提供查询、创建、更新、设默认、删除等方法
其中最关键的字段是：config_json，如果 config_json.context.tools 没有配置育种工具，那么即使 breeding/tools.py 已注册，模型也不一定能看到它们

后端配置线：
AgentConfigRepository.create/update
↓
保存 config_json
↓
config_json["context"]["tools"]
↓
chat_service.py 读取 config_item.config_json["context"]
↓
_build_agent_input_context()
↓
BaseContext.update_from_dict()
↓
context.tools
↓
RuntimeConfigMiddleware.get_tools_from_context()
↓
模型可见工具

前端当前走的运行线：
breeding_workbench_api.js
↓
meta.allowed_tools
↓
agent_run_service.py input_payload["meta"]
↓
run_worker.py meta
↓
stream_agent_chat(meta)

后续优化：在 breeding-workbench 场景下，把 meta.allowed_tools 映射到 input_context["tools"]
"""


# 默认配置名称
DEFAULT_CONFIG_NAME = "初始配置"


class AgentConfigRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # 根据 department_id 和 agent_id，列出某个部门下、某个 Agent 的所有配置
    async def list_by_department_agent(self, *, department_id: int, agent_id: str) -> list[AgentConfig]:
        result = await self.db.execute(
            select(AgentConfig)
            .where(AgentConfig.department_id == department_id, AgentConfig.agent_id == agent_id)
            .order_by(AgentConfig.is_default.desc(), AgentConfig.id.asc())
        )
        return list(result.scalars().all())

    # 用于根据配置 ID 查询一条 AgentConfig 记录是否存在
    async def get_by_id(self, config_id: int) -> AgentConfig | None:
        result = await self.db.execute(select(AgentConfig).where(AgentConfig.id == config_id))
        return result.scalar_one_or_none()

    # 把某条配置设为默认配置
    # 通常逻辑是在同一个 department_id + agent_id 下：
    # 先把其他配置 is_default=False  再把当前配置 is_default=True
    async def set_default(self, *, config: AgentConfig, updated_by: str | None = None) -> AgentConfig:
        if config.is_default:
            return config

        now = utc_now_naive()

        # 先清空该部门+智能体的所有默认配置
        await self.db.execute(
            update(AgentConfig)
            .where(
                AgentConfig.department_id == config.department_id,
                AgentConfig.agent_id == config.agent_id,
            )
            .values(is_default=False, updated_at=now, updated_by=updated_by)
        )

        # 再设置目标配置为默认
        config.is_default = True
        config.updated_at = now
        config.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def get_default(self, *, department_id: int, agent_id: str) -> AgentConfig | None:
        result = await self.db.execute(
            select(AgentConfig).where(
                AgentConfig.department_id == department_id,
                AgentConfig.agent_id == agent_id,
                AgentConfig.is_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # 获取某个部门、某个 Agent 的默认配置；如果不存在，就自动创建一条默认配置
    async def get_or_create_default(
        self,
        *,
        department_id: int,
        agent_id: str,
        created_by: str | None = None,
    ) -> AgentConfig:
        existing = await self.get_default(department_id=department_id, agent_id=agent_id)
        if existing:
            return existing

        items = await self.list_by_department_agent(department_id=department_id, agent_id=agent_id)
        if items:
            return items[0]

        config = AgentConfig(
            department_id=department_id,
            agent_id=agent_id,
            name=DEFAULT_CONFIG_NAME,
            description=None,
            icon=None,
            pics=[],
            examples=[],
            config_json={},
            is_default=True,
            created_by=created_by,
            updated_by=created_by,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def _name_exists(self, *, department_id: int, agent_id: str, name: str, exclude_id: int | None) -> bool:
        stmt = select(AgentConfig.id).where(
            AgentConfig.department_id == department_id,
            AgentConfig.agent_id == agent_id,
            AgentConfig.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(AgentConfig.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def ensure_unique_name(
        self,
        *,
        department_id: int,
        agent_id: str,
        desired_name: str,
        exclude_id: int | None = None,
    ) -> str:
        candidate = desired_name.strip() or "未命名配置"
        if not await self._name_exists(
            department_id=department_id, agent_id=agent_id, name=candidate, exclude_id=exclude_id
        ):
            return candidate

        base = f"{candidate}-副本"
        if not await self._name_exists(
            department_id=department_id, agent_id=agent_id, name=base, exclude_id=exclude_id
        ):
            return base

        idx = 2
        while True:
            candidate2 = f"{base}{idx}"
            if not await self._name_exists(
                department_id=department_id, agent_id=agent_id, name=candidate2, exclude_id=exclude_id
            ):
                return candidate2
            idx += 1

    # 创建一条新的 Agent 配置。接收配置信息写入数据库
    async def create(
        self,
        *,
        department_id: int,
        agent_id: str,
        name: str,
        description: str | None = None,
        icon: str | None = None,
        pics: list[str] | None = None,
        examples: list[str] | None = None,
        config_json: dict | None = None,
        is_default: bool = False,
        created_by: str | None = None,
    ) -> AgentConfig:
        unique_name = await self.ensure_unique_name(
            department_id=department_id,
            agent_id=agent_id,
            desired_name=name,
            exclude_id=None,
        )
        config = AgentConfig(
            department_id=department_id,
            agent_id=agent_id,
            name=unique_name,
            description=description,
            icon=icon,
            pics=pics or [],
            examples=examples or [],
            config_json=config_json or {},
            is_default=bool(is_default),
            created_by=created_by,
            updated_by=created_by,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    # 更新已有的 Agent 配置
    async def update(
        self,
        config: AgentConfig,
        *,
        name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        pics: list[str] | None = None,
        examples: list[str] | None = None,
        config_json: dict | None = None,
        updated_by: str | None = None,
    ) -> AgentConfig:
        if name is not None:
            config.name = await self.ensure_unique_name(
                department_id=config.department_id,
                agent_id=config.agent_id,
                desired_name=name,
                exclude_id=config.id,
            )
        if description is not None:
            config.description = description
        if icon is not None:
            config.icon = icon
        if pics is not None:
            config.pics = pics
        if examples is not None:
            config.examples = examples
        if config_json is not None:
            config.config_json = config_json

        config.updated_by = updated_by
        config.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def delete(self, *, config: AgentConfig, updated_by: str | None = None) -> None:
        department_id = config.department_id
        agent_id = config.agent_id
        was_default = bool(config.is_default)

        await self.db.delete(config)
        await self.db.commit()

        remaining = await self.list_by_department_agent(department_id=department_id, agent_id=agent_id)
        if not remaining:
            await self.get_or_create_default(department_id=department_id, agent_id=agent_id, created_by=updated_by)
            return

        if was_default:
            await self.set_default(config=remaining[0], updated_by=updated_by)
