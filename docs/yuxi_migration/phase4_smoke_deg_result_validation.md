# Phase 4 Smoke DEG Result Validation

## 当前运行模式

- 项目：Houji-YuXi
- 前端：本地 `web` 开发服务
- 后端：Docker Compose 提供的 api / worker
- 当前工作分支：`feature/yuxi-smoke-flavonoid-tool`

## 相关提交

- `8220f30 Add smoke flavonoid breeding advice tool`
- `9dfd7bb Disable thinking for DeepSeek V4 Pro tool calls`

## 云雾中转与模型状态

- 云雾中转已配置完成
- `yunwu:deepseek-chat` 已验证可用
- `yunwu:deepseek-v4-pro` 之前在 tool-calling 后续续写时触发 `reasoning_content` 报错
- 已在 `backend/package/yuxi/agents/models.py` 中对 `deepseek-v4-pro` 采用禁用 thinking 的最小兼容修复

## Tool 与页面状态

- `smoke_flavonoid_breeding_advice` 已接入 YuXi
- Tools 页面可见 `Smoke 黄酮育种建议`
- Agent 已能绑定 `smoke_flavonoid_breeding_advice`
- 页面已能调用该 Tool

## smoke DEG 流程结果

- smoke DEG 流程已跑通
- `significant_de_genes.tsv` 已生成
- 路径：
  - `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/significant_de_genes.tsv`
  - `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/de_pipeline_out/04_de/significant_de_genes.tsv`
  - `/tmp/yuxi_runs/smoke_de_out/significant_de_genes.tsv`
  - `/tmp/yuxi_runs/smoke_de_out/04_de/significant_de_genes.tsv`
- `Si9g037800` 出现在 `significant_de_genes.tsv` 中
- 页面输出包含 `Si9g037800`、`群体`、`黄酮`

## 守卫检查

- `guard_result.json` 的 `passed=true`
- 当前仍未补齐真实 DOI
- 当前仍未补齐引用原文
- 当前不能声称完成群体验证
- 当前不能声称完成湿实验验证
- 当前不能声称最终 KASP/CAPS 标记开发已完成

## 临时环境说明

- `api-dev` 内通过 `apt-get` 临时补齐了 smoke DEG 流程依赖
- 已安装：
  - `hisat2-build`
  - `hisat2`
  - `samtools`
  - `featureCounts`
  - `Rscript`
- 这只是临时演示环境，后续需要整理成可复现的环境方案

## 下一步计划

1. 补真实 DOI 和引用原文
2. 将参考基因组、转录组、代谢组拆成多个 YuXi Tools
3. 接入 artifacts
4. 未来再做育种工作台页面
