# Phase 6 Demo Acceptance and Runbook

## 当前主项目

- 主集成项目：`/home/li/projects/Houji-Breeding-Assistant`
- ` /tmp/Yuxi ` 仅作为历史参考，不再作为运行项目
- 当前分支：`feature/yuxi-smoke-flavonoid-tool`

## 验收清单

### 已完成的功能链路

- 左侧菜单已包含：
  - 创建新对话
  - 工作区
  - 知识库 / 知识图谱
  - 扩展管理
  - 模型配置
  - Dashboard
- 图谱页面可访问：`/graph`
- 扩展管理可访问：`/extensions`
- `smoke_flavonoid_breeding_advice` Tool 可见
- Agent 能调用 `smoke_flavonoid_breeding_advice`
- 云雾中转模型可用
- `yunwu:deepseek-v4-pro` 已通过禁用 thinking 修复 tool-calling
- smoke DEG 流程已跑通
- `significant_de_genes.tsv` 已生成并被读取
- `Si9g037800` 出现在 `significant_de_genes.tsv`
- Tool 输出包含 `Si9g037800`、`群体`、`黄酮`
- `verified_literature_evidence.tsv` 已放入 smoke 数据目录
- Tool 已能读取真实 DOI 和 `quoted_sentence`
- `guard_result.json` `passed=true`

### 当前真实文献证据

- DOI: `10.3390/life11060578`
  - quoted_sentence: `The yellow pigment mainly includes carotenoids (lutein and zeaxanthin) and flavonoids.`
  - evidence_level: `crop_trait_background`
- DOI: `10.1186/s12864-025-11780-x`
  - quoted_sentence: `Foxtail millet (Setaria italica L.), a traditional Chinese crop, is valued for its rich abundance of health-beneficial compounds (e.g., flavonoids).`
  - evidence_level: `pathway_background`

### 严格边界

- 两条文献都是背景证据，不是 `Si9g037800` 直接功能验证
- 不能声称完成群体验证
- 不能声称完成湿实验验证
- 不能声称最终 `KASP/CAPS` 标记已开发
- 不能把背景证据写成 `Si9g037800` 直接证据
- 当前未接入 artifacts
- 当前尚未拆分参考基因组、转录组、代谢组、育种建议多个 Tool
- 当前生信依赖仍是 api-dev 容器内临时安装，不是长期可复现方案

## 可复现运行说明

### 后端启动

```bash
cd /home/li/projects/Houji-Breeding-Assistant
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY=localhost,127.0.0.1,0.0.0.0,::1,192.168.248.132
export no_proxy=localhost,127.0.0.1,0.0.0.0,::1,192.168.248.132
export YUNWU_API_KEY="你的云雾中转真实 API Key"
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d api worker
curl --noproxy "*" -i http://127.0.0.1:5050/api/system/health | head -80
```

### 前端启动

```bash
cd /home/li/projects/Houji-Breeding-Assistant/web
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY=localhost,127.0.0.1,0.0.0.0,::1,192.168.248.132
export no_proxy=localhost,127.0.0.1,0.0.0.0,::1,192.168.248.132
VITE_API_URL=http://127.0.0.1:5050 pnpm run dev -- --host 0.0.0.0
```

### 浏览器入口

- 首页 / 对话页面
- `/graph` 知识图谱
- `/extensions` 扩展管理
- `/model-config` 模型配置

## 演示步骤

1. 打开模型配置，确认云雾中转模型可用。
2. 打开扩展管理，确认 `Smoke 黄酮育种建议` Tool 可见。
3. 新建对话，选择 `yunwu:deepseek-v4-pro`。
4. 输入：

   ```text
   请根据 smoke 数据给出一些育种建议，性状是黄酮相关。请优先调用 smoke_flavonoid_breeding_advice 工具。
   ```

5. 检查回答中包含：
   - `Si9g037800`
   - `群体`
   - `黄酮`
   - `significant_de_genes.tsv`
   - `DOI`
   - `引用原文`
6. 检查回答中不能出现：
   - 已完成群体验证
   - 已完成湿实验验证
   - 最终 `KASP/CAPS` 标记已开发
   - `Si9g037800` 已被文献直接功能验证

## 当前证据链

- `genome.gff` / `xiaomi_T2T_Annotation.smoke_genes.txt` 中有 `Si9g037800` 记录
- `significant_de_genes.tsv` 中有 `Si9g037800`
- `metabolome_raw_3372.tsv` 作为黄酮背景代谢数据
- `verified_literature_evidence.tsv` 中有两条真实 DOI 和原文句子
- 两条文献均为背景证据，不是 `Si9g037800` 直接证据

## 输出文件

- `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/breeding_advice.md`
- `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/significant_de_genes.tsv`
- `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/guard_result.json`
- `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/run_manifest.json`
- `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice/run.log`

## 当前限制

- 生信依赖仍是 api-dev 容器内临时安装，不是长期可复现方案
- 文献证据是背景级，不是 `gene_specific`
- 未完成群体验证
- 未完成湿实验验证
- 未完成最终 `KASP/CAPS` 标记开发
- 尚未拆分参考基因组、转录组、代谢组、育种建议多个 Tool
- 尚未接入 artifacts

## 下一步计划

1. 整理生信依赖可复现方案
2. 拆分多个育种 Tools
3. 接入 artifacts
4. 后续迁移到实验室正式部署项目
