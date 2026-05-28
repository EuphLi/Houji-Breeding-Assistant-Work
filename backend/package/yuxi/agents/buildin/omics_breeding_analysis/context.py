from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from yuxi.agents import BaseContext


# 数据类装饰器  创建对象时，参数必须用关键字形式传入
@dataclass(kw_only=True)
class OmicsBreedingAnalysisContext(BaseContext):
    """多组学育种分析智能体配置。

    该 Context 只保存运行配置，不保存运行结果。

    设计原则：
    - trait 是动态性状，不固定为“黄酮”。
    - target genes 不在 Context 中写死，应由输入数据和 Evidence Pack 动态识别。
    - citation、guard 只是运行模式配置，具体结果应进入 graph state / artifacts / outputs。
    """

    trait: str = field(
        default="",
        metadata={
            "name": "目标性状",
            "description": "用户本轮关注的育种性状，例如黄酮相关、抗旱、产量等。",
        },
    )

    question: str = field(
        default="",
        metadata={
            "name": "用户问题",
            "description": "用户希望智能体回答的多组学育种分析问题。",
        },
    )

    transcriptome_result_path: str = field(
        default="/home/gem/user-data/outputs/significant_de_genes.tsv",
        metadata={
            "name": "转录组结果文件",
            "description": "固定转录组流程输出的 significant_de_genes.tsv 路径。",
        },
    )

    literature_evidence_path: str = field(
        default="/home/gem/user-data/uploads/verified_literature_evidence.tsv",
        metadata={
            "name": "已验证文献证据表",
            "description": "包含真实 DOI 和 quoted_sentence 的已验证文献证据文件。",
        },
    )

    metabolome_path: str = field(
        default="/home/gem/user-data/uploads/metabolome_raw_3372.tsv",
        metadata={
            "name": "代谢组文件",
            "description": "已有代谢组结果文件，仅作为上下文证据，不由 LLM 替代专业分析流程。",
        },
    )

    reference_genome_path: str = field(
        default="",
        metadata={
            "name": "参考基因组文件",
            "description": "用户上传或默认示例中的 genome.fa 路径。",
        },
    )

    genome_gff_path: str = field(
        default="",
        metadata={
            "name": "GFF 注释文件",
            "description": "用户上传或默认示例中的 genome.gff 路径。",
        },
    )

    annotation_path: str = field(
        default="",
        metadata={
            "name": "功能注释文件",
            "description": "用户上传的功能注释文件路径。",
        },
    )

    sample_map_path: str = field(
        default="",
        metadata={
            "name": "样本分组文件",
            "description": "sampleName_clientId.txt 路径。",
        },
    )

    rnaseq_read_paths: list[str] = field(
        default_factory=list,
        metadata={
            "name": "RNA-seq Reads",
            "description": "用户上传的 FASTQ 文件路径列表。",
        },
    )

    upload_root: str = field(
        default="",
        metadata={
            "name": "上传根目录",
            "description": "本次 breeding-workbench 上传文件所在的服务端目录。",
        },
    )

    uploaded_file_count: int = field(
        default=0,
        metadata={
            "name": "上传文件数量",
            "description": "本次任务进入后端分析的上传文件总数。",
        },
    )

    genome_context_path: str = field(
        default="/home/gem/user-data/uploads/",
        metadata={
            "name": "基因组上下文路径",
            "description": "参考基因组、GFF 和功能注释所在路径，作为信息池使用。",
        },
    )

    evidence_pack_output_path: str = field(
        default="/home/gem/user-data/outputs/omics_evidence_pack.json",
        metadata={
            "name": "Evidence Pack 输出路径",
            "description": "标准化多组学证据包输出位置。",
        },
    )

    citation_mode: str = field(
        default="sentence",
        metadata={
            "name": "Citation 粒度",
            "description": "控制来源追溯粒度。",
            "options": ["sentence", "short_clause"],
        },
    )

    guard_mode: str = field(
        default="strict",
        metadata={
            "name": "Guard 模式",
            "description": "控制输出边界检查强度。",
            "options": ["normal", "strict"],
        },
    )

    # 从 OmicsBreedingAnalysisContext 中删除自定义 mcps 字段，先继承 BaseContext 自带的 mcps。
    # mcps: Annotated[list[str], {"__template_metadata__": {"kind": "mcps"}}] = field(
    #     default_factory=list,
    #     metadata={
    #         "name": "MCP服务器",
    #         "description": "可选外部 MCP 服务器列表。第一版可为空。",
    #         "options": [],
    #     },
    # )
