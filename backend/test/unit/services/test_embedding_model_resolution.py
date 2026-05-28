import os

os.environ.setdefault("SILICONFLOW_API_KEY", "test-key")

from yuxi.models.embed import get_embedding_model_info_by_id, resolve_embedding_model_id
from yuxi.services.model_cache import ModelInfo


def test_resolve_embedding_model_id_accepts_cached_v2_spec(monkeypatch):
    info = ModelInfo(
        provider_id="siliconflow-cn",
        model_id="Pro/BAAI/bge-m3",
        model_type="embedding",
        display_name="Pro/BAAI/bge-m3",
        api_key="test-key",
        base_url="https://api.siliconflow.cn/v1/embeddings",
        provider_type="openai",
        dimension=1024,
        batch_size=40,
    )
    monkeypatch.setattr("yuxi.services.model_cache.model_cache.get_model_info", lambda spec: info)

    assert resolve_embedding_model_id("siliconflow-cn:Pro/BAAI/bge-m3") == "siliconflow-cn:Pro/BAAI/bge-m3"

    embed_info = get_embedding_model_info_by_id("siliconflow-cn:Pro/BAAI/bge-m3")
    assert embed_info["model_id"] == "siliconflow-cn:Pro/BAAI/bge-m3"
    assert embed_info["name"] == "Pro/BAAI/bge-m3"
    assert embed_info["dimension"] == 1024


def test_resolve_embedding_model_id_falls_back_to_v1_alias_when_cache_misses(monkeypatch):
    monkeypatch.setattr("yuxi.services.model_cache.model_cache.get_model_info", lambda spec: None)

    assert resolve_embedding_model_id("siliconflow-cn:Pro/BAAI/bge-m3") == "siliconflow/Pro/BAAI/bge-m3"

    embed_info = get_embedding_model_info_by_id("siliconflow-cn:Pro/BAAI/bge-m3")
    assert embed_info["name"] == "Pro/BAAI/bge-m3"
    assert embed_info["dimension"] == 1024


def test_resolve_embedding_model_id_accepts_providerless_alias():
    assert resolve_embedding_model_id("Pro/BAAI/bge-m3") == "siliconflow/Pro/BAAI/bge-m3"
    assert resolve_embedding_model_id("BAAI/bge-m3") == "siliconflow/BAAI/bge-m3"
