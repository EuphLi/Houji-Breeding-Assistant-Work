# Phase 5 Verified Literature Evidence

## 当前状态

- 项目：Houji-YuXi
- 分支：`feature/yuxi-smoke-flavonoid-tool`
- smoke_flavonoid_breeding_advice 已能读取 `data_dir/verified_literature_evidence.tsv`
- 当前烟雾数据目录：
  - `/mnt/yuxi-breeding-data/smoke_test_minimal/Si9g037800_smoke_test_minimal/verified_literature_evidence.tsv`

## 已接入的真实文献证据

### 1. Foxtail millet flavonoid background

- DOI: `10.3390/life11060578`
- title: `Comparative Analysis of Flavonoid Metabolites in Foxtail Millet (Setaria italica) with Different Eating Quality`
- quoted_sentence: `The yellow pigment mainly includes carotenoids (lutein and zeaxanthin) and flavonoids.`
- evidence_level: `crop_trait_background`
- note: 谷子黄酮背景证据，不是 `Si9g037800` 直接功能验证。

### 2. Foxtail millet flavonoid biosynthesis background

- DOI: `10.1186/s12864-025-11780-x`
- title: `Targeted metabolomic and transcriptomic analyses provide insights into flavonoid biosynthesis in the grain of Foxtail millet`
- quoted_sentence: `Foxtail millet (Setaria italica L.), a traditional Chinese crop, is valued for its rich abundance of health-beneficial compounds (e.g., flavonoids).`
- evidence_level: `pathway_background`
- note: 谷子黄酮生物合成背景证据，不是 `Si9g037800` 直接功能验证。

## Tool 读取验证

- `smoke_flavonoid_breeding_advice` 已成功读取真实 DOI 与 `quoted_sentence`
- 输出中的文献证据段已展示真实 DOI 和原文
- `guard_result.json` 仍为 `passed=true`

## 输出边界

- 输出包含 `Si9g037800`
- 输出包含 `群体`
- 输出包含 `黄酮`
- 两条文献都只是背景证据
- 不能写成 `Si9g037800` 直接功能验证
- 仍未完成群体验证
- 仍未完成湿实验验证
- 仍未完成最终 `KASP/CAPS` 标记开发

## 下一步

1. 如果后续拿到更直接的 `Si9g037800` 文献，再补 `gene_specific` 证据
2. 否则保持当前“背景证据”表述，不扩展到直接功能结论
