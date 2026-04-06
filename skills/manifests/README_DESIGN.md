## Skill manifest 目录规范

### 1. 目的
- 明确内置 skill 的文件命名与版本管理规则

### 2. 命名建议
- `skills/manifests/{skill_id}/skill_manifest_v{version}.json|yaml`
- 或统一放入一个文件夹中：
  - `skills/manifests/invoice_helper_v3.yaml`

### 3. 验收标准
- 任意 manifest 必须能被 Skills Registry 加载并通过 schema 校验
- 版本字段必须存在且可追溯写入 trace

### 4. 推荐模版（YAML）
可直接复制后按需替换字段：

```yaml
id: invoice_helper
version: 1
description: "发票审核与报销问答增强"

trigger:
  keywords:
    - 发票
    - 税号
    - 报销
  intent_labels:
    - finance.invoice_check
  # match_rules 为可选项，按实现支持的简单规则填写
  # match_rules:
  #   any_of:
  #     - "提到税号"
  #     - "提到开票日期"

prompt_addon: |
  你是发票审核助手。优先执行以下策略：
  1) 明确提取发票代码、发票号码、税号、金额、日期。
  2) 对缺失字段先提示补充，再给结论。
  3) 结论使用“通过/待补充/疑似异常”三档。

retrieval_hints:
  query_rewrite: "围绕发票字段标准、税务术语、报销制度进行改写"
  preferred_terms:
    - 发票代码
    - 发票号码
    - 纳税人识别号
    - 价税合计
  # 可选：如果实现支持，可加检索权重建议
  # weights:
  #   glossary: 1.2
  #   policy: 1.0

tools_allowlist:
  - ocr_lookup
  - invoice_validator

# 可选：控制 prompt_addon 注入上限，避免成本失控
max_addon_tokens: 220
```

### 5. 字段填写建议
- `id`：稳定唯一，建议使用小写下划线命名，不要带版本号（版本放在 `version`）。
- `version`：整数递增或 semver；每次行为变更必须递增。
- `trigger`：先从 `keywords` 开始，后续再引入更复杂 `match_rules`。
- `prompt_addon`：只写任务偏置，不写“解锁工具/修改系统策略”等越权内容。
- `retrieval_hints`：写“检索提示”，不要写执行流程。
- `tools_allowlist`：只列该 skill 真实需要的最小工具集合（最小权限原则）。

