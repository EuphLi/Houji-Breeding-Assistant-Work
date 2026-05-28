from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.workflow import (
    prepare_cited_guarded_omics_analysis_from_context,
)
from yuxi.agents.toolkits.registry import tool

"""
omics_analysis.py 本质上是：
YuXi Tool 注册层 + 输入校验层 + workflow 包装层
正式 YuXi Tool 入口如何定义、如何调用 workflow、如何返回前端需要的结果。
chat_service.py
  _build_direct_breeding_tool_input()
    ↓
omics_breeding_analysis_run.invoke({"input": tool_input})
    ↓
omics_analysis.py
  omics_breeding_analysis_run()
    ↓
_run_omics_breeding_analysis_impl()
    ↓
prepare_cited_guarded_omics_analysis_from_context()
    ↓
workflow.py
"""

# YuXi Tool 的输入合同，前端和 Agent 都可以根据它知道这个工具需要哪些参数
class OmicsBreedingAnalysisRunInput(BaseModel):
    """多组学育种分析 Tool 输入参数。

    这个 Tool 是新 OmicsBreedingAnalysisAgent 的正式工具入口。
    它不复用旧建议逻辑，而是调用新的 Evidence Pack + Citation + Guard workflow。
    """

    trait: str = Field(
        default="",
        description="目标性状，例如 黄酮相关、抗旱、产量等。",
    )
    question: str = Field(
        default="",
        description="用户本轮希望回答的多组学育种分析问题。",
    )
    transcriptome_result_path: str = Field(
        default="",
        description="significant_de_genes.tsv 文件路径。",
    )
    metabolome_path: str = Field(
        default="",
        description="代谢组结果文件路径；为空时仅记录为未提供。",
    )
    reference_genome_path: str = Field(
        default="",
        description="参考基因组 FASTA 路径。",
    )
    genome_gff_path: str = Field(
        default="",
        description="参考基因组 GFF 路径。",
    )
    annotation_path: str = Field(
        default="",
        description="功能注释文件路径。",
    )
    sample_map_path: str = Field(
        default="",
        description="sampleName_clientId.txt 路径。",
    )
    rnaseq_read_paths: list[str] = Field(
        default_factory=list,
        description="上传到服务端的 RNA-seq FASTQ 文件路径列表。",
    )
    upload_root: str = Field(
        default="",
        description="本次 breeding-workbench 上传文件根目录。",
    )
    uploaded_file_count: int = Field(
        default=0,
        description="本次任务上传到服务端的文件总数。",
    )
    literature_evidence_path: str = Field(
        default="",
        description="verified_literature_evidence.tsv 文件路径。",
    )
    evidence_pack_output_path: str = Field(
        default="",
        description="omics_evidence_pack.json 输出路径；为空时写入 output_dir。",
    )
    output_dir: str = Field(
        default="/tmp/yuxi_runs/omics_breeding_analysis",
        description="final_result.json、answer_markdown.md、citation_result.json、guard_result.json 输出目录。",
    )
    use_llamaindex: bool = Field(
        default=False,
        description="是否尝试使用 LlamaIndex CitationQueryEngine；默认使用 mock fallback。",
    )
    model: str = Field(
        default="",
        description="可选，显式指定用于证据整合分析的模型；为空时使用 Context 默认模型。",
    )


# 内部实现层。它把用户输入路径和问题整理成 OmicsBreedingAnalysisContext，然后调用已经完成的：prepare_cited_guarded_omics_analysis_from_context()
# 这个工具不会重新写 Evidence Pack / Citation / Guard 逻辑，只是包装现有 workflow
def _run_omics_breeding_analysis_impl(
    *,
    trait: str,
    question: str,
    transcriptome_result_path: str,
    metabolome_path: str,
    reference_genome_path: str = "",
    genome_gff_path: str = "",
    annotation_path: str = "",
    sample_map_path: str = "",
    rnaseq_read_paths: list[str] | None = None,
    upload_root: str = "",
    uploaded_file_count: int = 0,
    literature_evidence_path: str = "",
    evidence_pack_output_path: str = "",
    output_dir: str = "",
    use_llamaindex: bool = False,
    model: str = "",
) -> dict[str, Any]:
    """执行新多组学育种分析 workflow。

    这是 Tool 的内部实现层，便于单元测试直接调用。
    """

    # 把 output_dir 转成绝对路径，并确保目录存在。
    out_path = Path(output_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    def _relative_to_data_dir(path_value: str, data_dir_path: Path) -> str:
        resolved = Path(path_value).expanduser().resolve()
        try:
            return str(resolved.relative_to(data_dir_path))
        except ValueError:
            return resolved.name

    # 决定 Evidence Pack 输出路径
    evidence_pack_path = (
        Path(evidence_pack_output_path).expanduser().resolve()
        if evidence_pack_output_path
        else out_path / "omics_evidence_pack.json"
    )

    rnaseq_read_paths = list(rnaseq_read_paths or [])

    transcriptome_pipeline_status = "not_enough_inputs"
    transcriptome_pipeline_details: dict[str, Any] = {}
    normalized_transcriptome_path = str(transcriptome_result_path or "").strip()
    if normalized_transcriptome_path and Path(normalized_transcriptome_path).is_file():
        transcriptome_pipeline_status = "skipped_existing_deg"
    elif upload_root and sample_map_path and genome_gff_path and reference_genome_path and rnaseq_read_paths:
        from yuxi.agents.toolkits.breeding.tools import breeding_transcriptome_deg

        data_dir_path = Path(upload_root).expanduser().resolve()
        fq_parent = Path(rnaseq_read_paths[0]).expanduser().resolve().parent if rnaseq_read_paths else data_dir_path / "fq"
        try:
            transcriptome_tool_result = breeding_transcriptome_deg.invoke(
                {
                    "data_dir": str(data_dir_path),
                    "fq_dir": _relative_to_data_dir(str(fq_parent), data_dir_path),
                    "sample_map": _relative_to_data_dir(sample_map_path, data_dir_path),
                    "genome_fa": _relative_to_data_dir(reference_genome_path, data_dir_path),
                    "genome_gff": _relative_to_data_dir(genome_gff_path, data_dir_path),
                    "out_dir": str(out_path / "transcriptome_deg"),
                    "threads": 8,
                    "run_pipeline": True,
                }
            )
            transcriptome_pipeline_details = transcriptome_tool_result or {}
            generated_path = str(transcriptome_tool_result.get("significant_de_genes_path") or "").strip()
            missing_tools = transcriptome_tool_result.get("missing_tools") or []
            if generated_path and Path(generated_path).is_file():
                normalized_transcriptome_path = generated_path
                transcriptome_pipeline_status = "completed"
            elif missing_tools:
                transcriptome_pipeline_status = "dependency_missing"
            else:
                transcriptome_pipeline_status = "failed"
        except Exception as exc:  # noqa: BLE001
            transcriptome_pipeline_status = "failed"
            transcriptome_pipeline_details = {"error": str(exc)}
    elif normalized_transcriptome_path:
        transcriptome_pipeline_status = "failed"

    # 构造 OmicsBreedingAnalysisContext
    context = OmicsBreedingAnalysisContext(
        trait=trait,
        question=question,
        transcriptome_result_path=normalized_transcriptome_path,
        metabolome_path=metabolome_path,
        reference_genome_path=reference_genome_path,
        genome_gff_path=genome_gff_path,
        annotation_path=annotation_path,
        sample_map_path=sample_map_path,
        rnaseq_read_paths=rnaseq_read_paths,
        upload_root=upload_root,
        uploaded_file_count=max(0, int(uploaded_file_count or 0)),
        literature_evidence_path=literature_evidence_path,
        evidence_pack_output_path=str(evidence_pack_path),
        model=model,
    )

    # 调用 workflow，是业务执行的真正入口
    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=use_llamaindex,
        output_dir=out_path,
    )

    summary = result.get("summary") or {}
    summary.update(
        {
            "transcriptome_pipeline_status": transcriptome_pipeline_status,
            "transcriptome_result_path": normalized_transcriptome_path,
            "upload_root": upload_root,
            "uploaded_file_count": max(0, int(uploaded_file_count or 0)),
            "sample_map_path": sample_map_path,
            "sample_map_path_exists": bool(sample_map_path) and Path(sample_map_path).is_file(),
            "rnaseq_read_count": len(rnaseq_read_paths or []),
            "reference_file_count": len(
                [
                    path
                    for path in [reference_genome_path, genome_gff_path, annotation_path]
                    if str(path or "").strip()
                ]
            ),
            "citation_backend": result.get("citation_backend") or result.get("backend") or "",
            "llamaindex_available": bool(result.get("llamaindex_available")),
        }
    )
    if transcriptome_pipeline_details:
        summary["transcriptome_pipeline_details"] = transcriptome_pipeline_details
    result["summary"] = summary

    frontend_payload = result.get("frontend_payload") or {}
    frontend_payload["summary"] = summary
    result["frontend_payload"] = frontend_payload

    if result.get("frontend_payload_path"):
        Path(result["frontend_payload_path"]).write_text(
            json.dumps(frontend_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    final_result_path = out_path / "final_result.json"
    if final_result_path.exists():
        persisted = json.loads(final_result_path.read_text(encoding="utf-8"))
        persisted["summary"] = summary
        persisted["frontend_payload"] = frontend_payload
        final_result_path.write_text(json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8")

    # 把 workflow 的 result 挑选并整理成工具返回值
    # 这些字段会回到：
    # chat_service.py
    #   tool_result
    #     ↓
    # _save_direct_breeding_workbench_tool_messages()
    #     ↓
    # tool message / assistant message / frontend_payload
    #     ↓
    # 前端 buildRunSnapshot()
    return {
        "status": result["status"],
        "backend": result["backend"],
        "llamaindex_available": result["llamaindex_available"],
        "answer_markdown": result["answer_markdown"],
        "summary": result["summary"], # 运行诊断和数据来源信息
        "guard_result": result["guard_result"],
        "citations": result["citations"],
        "literature_cards": result["literature_cards"],
        "claim_trace": result["claim_trace"],
        "source_nodes": result.get("source_nodes") or [],
        "frontend_payload": result.get("frontend_payload") or {},
        "evidence_pack_path": result["evidence_pack_path"],
        "answer_markdown_path": result["answer_markdown_path"], # 页面正文
        "citation_result_path": result["citation_result_path"],
        "guard_result_path": result["guard_result_path"],
        "frontend_payload_path": result.get("frontend_payload_path", ""), # 前端结构化 payload
        "final_result_path": str(out_path / "final_result.json"), # 最终结果 JSON 路径
        "warnings": result["warnings"],
        "artifacts": result["artifacts"], # 输出文件列表
    }


# 真正注册给 YuXi Tool Registry 的函数,有 @tool(...) 装饰器，所以被导入后会进入 YuXi 工具系统
# Tool 入口保持薄，真正逻辑下沉到 _run_omics_breeding_analysis_impl() 和 workflow。
@tool(
    category="breeding",
    tags=["多组学", "育种分析", "citation", "guard"],
    display_name="多组学育种分析",
)
def omics_breeding_analysis_run(
    input: OmicsBreedingAnalysisRunInput,
) -> dict[str, Any]:
    """运行多组学育种分析，生成带 citation 和 Guard 的结构化结果。"""

    # 把 input.xxx 拆出来，传给内部实现函数
    try:
        return _run_omics_breeding_analysis_impl(
            trait=input.trait,
            question=input.question,
            transcriptome_result_path=input.transcriptome_result_path,
            metabolome_path=input.metabolome_path,
            reference_genome_path=input.reference_genome_path,
            genome_gff_path=input.genome_gff_path,
            annotation_path=input.annotation_path,
            sample_map_path=input.sample_map_path,
            rnaseq_read_paths=input.rnaseq_read_paths,
            upload_root=input.upload_root,
            uploaded_file_count=input.uploaded_file_count,
            literature_evidence_path=input.literature_evidence_path,
            evidence_pack_output_path=input.evidence_pack_output_path,
            output_dir=input.output_dir,
            use_llamaindex=input.use_llamaindex,
            model=input.model,
        )
    # 捕获异常，返回 status=error
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error": str(exc),
            "artifacts": [],
        }
