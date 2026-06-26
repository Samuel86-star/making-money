# AI Handoff 流程指南

## 概述

单股调研简报（Brief）采用**人-AI 手递手**模式：Python 脚本负责数据采集和模板渲染，Claude Code 负责跨信号综合分析。两者通过 JSON 快照文件对接。

## 工作流

```
[Python] build_snapshot(code)        → snapshot.json  (ai_analysis: null)
         render_markdown(snapshot)   → snippet.md     (含占位 "等分析")
[Claude] 读取 snapshot.json,
         分析五大维度信号,
         写回 ai_analysis 字段        → snapshot.json  (ai_analysis: "建议...")
[Python] 重新读取 snapshot.json,
         render_markdown(snapshot)   → snippet.md     (AI 段已填充)
```

## 终端命令

```bash
# 1. 生成调研快照（含占位）
python -m py.brief 000034

# 2. 读取 JSON 快照内容
cat data/screen/briefs/000034/2026-06-26.json

# 3. 提示 Claude Code 分析
#    用户发送: "analyze 000034"
#    Claude 读取 JSON → 生成 ai_analysis → save_snapshot 写回

# 4. 重新生成 MD（AI 段填充）
python -m py.brief 000034
```

## JSON 快照关键字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `ai_analysis` | string\|null | Claude 填写的分析文本，null 表示未分析 |
| `ai_analysis_meta.analyzed_at` | string ISO | 分析完成时间戳 |
| `risks` | list[str] | 数据层发现的客观风险点（脚本级） |

## 占位识别

当 `ai_analysis` 为 `null` 时，MD 中生成：

```html
<!-- 等分析:让 Claude Code 读取本 JSON 快照后填充,会写回 ai_analysis 字段 -->
```

Claude 检测到此注释即知需要执行跨信号分析。