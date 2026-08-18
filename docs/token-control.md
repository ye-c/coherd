# Token 消耗控制

> 目标：在不影响工作质量前提下，降低 coherd 集群的 token 消耗。

## 1. 契约内优化（零成本，立即生效）

严格走 §3 路径式交审：executor 交审消息只附 **DoD + 输出路径 + 关键取舍一句**，不转发产物正文。

- coordinator 不中转产物给 reviewer（executor 直交，§2 已在契约内）。
- 关键在执行：executor 交审消息精简到路径级，不带代码片段。

## 2. 通信精简

- 结论结构化：`approve: <理由要点>` / `revise: <问题清单逐条>`。
- agent 间消息用要点式，避免叙述铺陈。
- executor 交审消息**底线**：保 DoD + 路径 + 关键取舍一句，不可瘦到只剩路径。
- 回复对称义务按任务闭环计（§2），不重发、不纯 ack。

## 3. 规模缩放（§6 加硬判据）

简单任务跳过 reviewer 全链路（coordinator → executor → 交付）的硬判据：

```text
≤2 文件改动 + 无安全/正确性敏感面
```

任一条件不满足 → 必走 executor → reviewer → coordinator 全链路。

## 4. 输入端控制（token 大头在此）

- 消息引用路径，不贴大文件正文。
- 交审附 `git diff` 范围，reviewer 只读变更行。
- 长任务串轮换 session，防上下文膨胀。

## 5. 优先级（投资分派质量优先）

```text
1（契约内优化）→ 2（通信精简）→ 3（规模缩放判据）→ 4（输入端控制）
```

> **核心原则**：revise 循环最贵——一次返工的 token 消耗 > 一切通信压缩的收益。投资分派质量（清晰 objective / 可测 DoD / 精确边界）优先于压缩单条消息。

## 不做：静态模型分层

静态按角色降配（coordinator=haiku / reviewer=sonnet / executor=opus）**不做**——

- reviewer 降 sonnet 毁审查质量 = 毁架构核心（角色分离）。
- coordinator 降 haiku 致烂分派 → revise 循环烧更多 token。

模型分层属用户 CLI 层配置（自行设 `COHERD_*_CMD` 指向不同 wrapper），coherd 框架不接管、不动态切换。
