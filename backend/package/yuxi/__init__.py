from dotenv import load_dotenv

load_dotenv(".env", override=True)

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from importlib import import_module  # noqa: E402
from types import ModuleType  # noqa: E402
import sys  # noqa: E402

try:
    from importlib.metadata import version

    __version__ = version("yuxi")
except Exception:
    __version__ = "unknown"

executor = ThreadPoolExecutor()  # noqa: E402


class _LazyConfigProxy:
    def _get_config(self):
        return import_module("yuxi.config").config

    def __getattr__(self, name):
        return getattr(self._get_config(), name)

    def __setattr__(self, name, value):
        return setattr(self._get_config(), name, value)

    def __repr__(self):
        return repr(self._get_config())


_config_proxy = _LazyConfigProxy()


class _YuxiModule(ModuleType):
    def __getattribute__(self, name):
        if name == "config":
            return ModuleType.__getattribute__(self, "_config_proxy")
        return ModuleType.__getattribute__(self, name)


sys.modules[__name__].__class__ = _YuxiModule
config = _config_proxy


def get_version():
    """Return the Yuxi version."""
    return __version__


def __getattr__(name: str):
    if name == "agents":
        return import_module("yuxi.agents")
    if name in {"graph_base", "knowledge_base"}:
        knowledge = import_module("yuxi.knowledge")
        return getattr(knowledge, name)
    raise AttributeError(f"module 'yuxi' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | {"agents", "config", "graph_base", "knowledge_base"})


__all__ = ["config", "agents", "graph_base", "knowledge_base"]
