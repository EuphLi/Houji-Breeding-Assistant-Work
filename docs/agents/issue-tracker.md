# Issue tracker：本地 Markdown

本仓库的 Issue 和 PRD 以 Markdown 文件形式存放在 `.scratch/` 目录下。

## 规范

- 每个功能一个目录：`.scratch/<feature-slug>/`
- PRD 文件为：`.scratch/<feature-slug>/PRD.md`
- 实现 Issue 为：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 开始编号
- 分类状态记录在每个 Issue 文件顶部的 `Status:` 行中（角色字符串见 `triage-labels.md`）
- 评论和对话历史追加到文件底部 `## Comments` 标题下

## 当技能要求 "发布到 Issue tracker" 时

在 `.scratch/<feature-slug>/` 下创建新文件（如目录不存在则一并创建）。

## 当技能要求 "获取相关工单" 时

读取所引用路径的文件。用户通常会直接传递路径或 Issue 编号。
