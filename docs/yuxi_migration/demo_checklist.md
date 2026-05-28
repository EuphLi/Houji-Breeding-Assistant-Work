# YuXi 育种智能体演示 Checklist

## 1. 启动前检查

- [ ] 后端 Docker `api/worker` 已运行
- [ ] 前端已从 `/home/li/projects/Houji-Breeding-Assistant/web` 启动
- [ ] `YUNWU_API_KEY` 已进入 `api-dev`
- [ ] `http://127.0.0.1:5050/api/system/health` 返回 `200`
- [ ] `/tmp/yuxi_runs/smoke_flavonoid_breeding_advice` 下输出文件存在

## 2. 浏览器入口

- [ ] 首页 / 对话
- [ ] `/model-config`
- [ ] `/extensions`
- [ ] `/graph`

## 3. 演示顺序

1. 打开模型配置，确认云雾模型可用。
2. 打开扩展管理，确认 `Smoke 黄酮育种建议` Tool 可见。
3. 打开知识图谱，展示图谱页面。
4. 创建新对话。
5. 选择 `yunwu:deepseek-v4-pro`。
6. 输入：

   ```text
   请根据 smoke 数据给出一些育种建议，性状是黄酮相关。请优先调用 smoke_flavonoid_breeding_advice 工具。
   ```

## 4. 必须检查输出包含

- `Si9g037800`
- `群体`
- `黄酮`
- `significant_de_genes.tsv`
- `DOI`
- `引用原文`
- `guard_result passed=true`

## 5. 必须避免的表述

- 已完成群体验证
- 已完成湿实验验证
- 最终 `KASP/CAPS` 标记已开发
- `Si9g037800` 已被文献直接功能验证
- 背景文献被说成直接证据

## 6. 老师可能问的问题和标准回答

- 为什么不再用 Gradio？
  - 现在演示链路已经统一到 Houji-YuXi，便于复用前端、Agent、Tool 和模型配置。
- YuXi 里 Tool 和 Agent 是怎么配合的？
  - Agent 选择并调用 Tool，Tool 负责返回结构化结果，再由 Agent 继续组织回答。
- 现在的 DOI 是否真实？
  - 是，当前证据文件里的 DOI 与引用原文都来自可核验文献。
- `Si9g037800` 是否已经被实验验证？
  - 没有，当前只是在 smoke 数据链路里作为候选基因展示。
- 当前 smoke 流程和真实生产流程有什么区别？
  - smoke 只验证最小数据链路和输出边界，不代表完整生产级结论。
- 后续如何拆分参考基因组、转录组、代谢组、育种建议多个 Tool？
  - 后续按职责拆分，分别承担数据读取、证据整理和育种建议生成。
