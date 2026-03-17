# MzAgentSub

MzAgentSub 当前提供的是 MzAgent 第一阶段 Python 主线下的最小正式实现面，覆盖协议层、运行时门禁、知识载体、主链样板与适配壳。

## 当前定位

- 当前仓库实现的是第一阶段最小正式实现面，不是生产可用的完整代理系统。
- 当前 `adapters` 主要用于协议归一与主链联调样板，默认不代表已接通真实外部服务。
- 当前 `orchestration` 提供的是单轮主链样板，不等价于完整多轮自治执行框架。
- 当前 `tests` 主要覆盖契约门禁、模块行为与最小编排样板，不等价于端到端集成测试。

## 当前范围

当前版本：`0.1.14`

已实现模块：

- `contracts`
  - 协议对象、字段约束、状态枚举
- `runtime`
  - 状态转移校验、追踪继承、回写门禁
- `orchestration`
  - `Planning -> ReAct -> Guardrails -> STM` 的单轮主链样板
  - `InMemorySTM / FileBackedSTM` 双模式状态载体
- `app`
  - CLI / Web 共用的运行时与会话服务层
- `knowledge`
  - 本地文档导入、分块与最小查询入口
- `adapters`
  - `tool / mcp / llm / skill / rag` 的统一输入输出壳
- `web`
  - 轻量 ASGI JSON API
  - 单页任务控制台与最小会话视图

当前未完全覆盖：

- 真实 MCP 工具调用仍依赖目标服务具备标准 MCP `tools/list` 与 `tools/call` 能力
- Skill 当前只完成目录扫描、元数据读取与资源暴露，尚未接入执行链路
- 生产级多会话 Web 服务、用户体系与复杂前端状态管理
- 生产级多轮自治执行

## 目录结构

```text
sub/MzAgentSub/
├── pyproject.toml
├── README.md
├── scripts/
│   ├── demo_adapters.py
│   ├── demo_pipeline.py
│   ├── test_adapters.sh
│   ├── test_all.sh
│   ├── test_contracts.sh
│   ├── test_integration.sh
│   ├── test_knowledge.sh
│   ├── test_live_llm.sh
│   ├── test_live_mcp.sh
│   ├── test_orchestration.sh
│   ├── test_perception.sh
│   ├── test_runtime.sh
│   ├── test_skills.sh
│   └── test_stm.sh
├── src/mz_agent/
│   ├── app/
│   ├── contracts/
│   ├── runtime/
│   ├── knowledge/
│   ├── orchestration/
│   ├── adapters/
│   └── web/
└── tests/
    ├── contracts/
    ├── adapters/
    ├── integration/
    ├── knowledge/
    ├── orchestration/
    ├── perception/
    ├── runtime/
    ├── skills/
    └── stm/
```

## 模块职责

### `contracts`

- 负责协议对象、字段存在性、可空规则和状态枚举。
- 对应路径：
  - `src/mz_agent/contracts`

### `runtime`

- 负责运行时硬门禁，包括：
  - 状态转移
  - 追踪继承
  - `STM` 回写时机
- 对应路径：
  - `src/mz_agent/runtime`

### `orchestration`

- 负责第一阶段最小主链样板：
  - `Planning`
  - `ReAct`
  - `Guardrails`
  - `STM`
  - `Pipeline`
- 对应路径：
  - `src/mz_agent/orchestration`

### `knowledge`

- 负责第一阶段最小知识库载体：
  - 文档导入
  - 文本分块
  - 查询命中对象返回
- 对应路径：
  - `src/mz_agent/knowledge`

### `app`

- 负责 CLI 与 Web 共用的运行时组装、单轮提交与会话查询能力。
- 对应路径：
  - `src/mz_agent/app`

### `adapters`

- 负责 `tool / mcp / llm / skill / rag` 的统一输入输出壳。
- 当前定位是样板与归一层，不是完整外部接入实现。
- 对应路径：
  - `src/mz_agent/adapters`

### `web`

- 负责第一阶段最小 Web 主入口：
  - `POST /api/round`
  - `GET /api/session/{session_id}/history`
  - `POST /api/session/{session_id}/reset`
  - `GET /api/session/{session_id}/status`
- 同时提供原生表单/轻量 JS 的单页任务控制台。
- 对应路径：
  - `src/mz_agent/web`

## 环境准备

要求：

- Python `3.10+`
- 建议在子仓目录执行命令：

```bash
cd /home/z/share/MzAgent/sub/MzAgentSub
```

安装依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## 最短启动路径

如果你是第一次使用，直接按下面 4 步操作：

1. 进入仓库并安装依赖

```bash
cd /home/z/share/MzAgent/sub/MzAgentSub
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

2. 复制示例环境文件

```bash
cp scripts/start_web.example.env .env
```

3. 修改 `.env`

- 如果你接反代站点：
  - 填 `LLM_MODEL_ID`
  - 填 `LLM_API_KEY`
  - 填 `LLM_BASE_URL`
- 如果你接原生 OpenAI：
  - 填 `LLM_MODEL_ID`
  - 填 `LLM_API_KEY`
  - `LLM_BASE_URL` 留空

4. 启动 Web

```bash
./scripts/start_web.sh
```

启动后浏览器访问：

```text
http://127.0.0.1:8000
```

如果你已经在页面里保存过多套配置方案，也可以指定默认 profile 启动：

```bash
./scripts/start_web.sh --profile proxy-demo
```

如需真实联调，请在子仓根目录放置 `.env`：

```dotenv
LLM_MODEL_ID=你的模型名
LLM_API_KEY=你的接口密钥
LLM_BASE_URL=你的 OpenAI Compatible Base URL
LLM_TIMEOUT=60
```

也可以直接复制仓库提供的示例模板：

```bash
cp scripts/start_web.example.env .env
```

当前同时支持从 `pyproject.toml` 读取 `mcp_servers.<name>` 配置；仓库内已预置 `cunzhi` 的 `stdio` 启动方式。

安装完成后可直接使用 CLI：

```bash
mz-agent --goal "搜索协议文档" --action-type tool --target search_docs
```

也可以启动 Web 主入口：

```bash
mz-agent-web --host 127.0.0.1 --port 8000
```

面向普通使用者，优先建议直接使用启动脚本：

```bash
./scripts/start_web.sh
```

支持的常用参数：

```bash
./scripts/start_web.sh --profile proxy-demo
./scripts/start_web.sh --host 0.0.0.0 --port 8010
./scripts/start_web.sh --no-live-llm
```

然后在浏览器访问：

```text
http://127.0.0.1:8000
```

CLI / REPL 现在保留为内部调试入口：

```bash
mz-agent --repl
```

## 按模块测试

### 1. 协议层测试 `contracts`

目标：

- 锁协议对象结构
- 锁 `extra='forbid'`
- 锁状态枚举和值域
- 锁 Guardrails 映射

对应测试：

- `tests/contracts/test_context_snapshot.py`
- `tests/contracts/test_plan_refs.py`
- `tests/contracts/test_guardrails_mapping.py`
- `tests/contracts/test_tooling_contracts.py`
- `tests/contracts/test_llm_contracts.py`

执行：

```bash
./scripts/test_contracts.sh
```

或：

```bash
pytest tests/contracts
```

### 2. 运行时门禁测试 `runtime`

目标：

- 锁状态迁移门禁
- 锁追踪继承规则
- 锁 `STM` 回写时机

对应测试：

- `tests/runtime/test_state_transitions.py`
- `tests/runtime/test_trace_inheritance.py`
- `tests/runtime/test_writeback_timing.py`

执行：

```bash
./scripts/test_runtime.sh
```

或：

```bash
pytest tests/runtime
```

### 3. 输入准备测试 `perception`

目标：

- 锁单轮输入进入快照时的最小规范化
- 锁 `tool / mcp` 的桥接参数生成
- 锁 `finish` 的草稿答案注入规则

对应测试：

- `tests/perception/test_round_preparation.py`

执行：

```bash
./scripts/test_perception.sh
```

或：

```bash
pytest tests/perception
```

### 4. STM 持久化测试 `stm`

目标：

- 锁 `FileBackedSTM` 的快照持久化与回读
- 锁对话历史写回与清理规则

对应测试：

- `tests/stm/test_persistence.py`

执行：

```bash
./scripts/test_stm.sh
```

或：

```bash
pytest tests/stm
```

### 5. 主链编排测试 `orchestration`

目标：

- 验证动作链：
  - `pre_action -> execute -> post_action -> writeback`
- 验证回答链：
  - `pre_answer -> output -> post_answer -> writeback`
- 验证 `Planning / ReAct / Guardrails / STM` 最小协作

对应测试：

- `tests/orchestration/test_pipeline.py`
- `tests/orchestration/test_engines.py`
- `tests/orchestration/test_repl_history.py`

执行：

```bash
./scripts/test_orchestration.sh
```

### 6. 适配层测试 `adapters`

目标：

- 验证 `tool / mcp / llm / skill / rag` 五类适配壳的标准化输出
- 验证错误码和降级分支

对应测试：

- `tests/adapters/test_adapters.py`
- `tests/adapters/test_adapter_errors.py`
- `tests/adapters/test_live_configuration.py`

执行：

```bash
./scripts/test_adapters.sh
```

### 7. 知识检索测试 `knowledge`

目标：

- 锁知识库载体的文档导入、分块与查询命中对象
- 锁 `KB -> RAG` 检索增强链的最小闭环
- 锁 `top_k / score_threshold / query rewrite` 的冻结语义
- 锁“无结果不等于错误”的边界

对应测试：

- `tests/knowledge/test_rag_adapter.py`

执行：

```bash
./scripts/test_knowledge.sh
```

或：

```bash
pytest tests/knowledge
```

### 8. Skill 装载测试 `skills`

目标：

- 锁目录扫描、frontmatter 元数据与资源清单暴露
- 锁 `SKL_001 ~ SKL_003` 的错误码语义
- 锁 Skill 只承担接入与暴露，不承担执行结果

对应测试：

- `tests/skills/test_skill_adapter.py`

执行：

```bash
./scripts/test_skills.sh
```

或：

```bash
pytest tests/skills
```

### 9. 集成回归测试 `integration`

目标：

- 锁 CLI 与 Web 入口的跨层闭环
- 锁运行时与 STM 文件持久化的真实接线
- 锁 Web 会话状态、澄清流与重置流

对应测试：

- `tests/integration/test_cli_roundtrip.py`
- `tests/integration/test_web_roundtrip.py`
- `tests/integration/test_web_session_resume.py`
- `tests/integration/test_web_clarify_flow.py`
- `tests/integration/test_web_session_controls.py`

执行：

```bash
./scripts/test_integration.sh
```

或：

```bash
pytest tests/integration
```

### 10. 测试映射速查表

| 测试域 | 目标摘要 | 测试文件 | 脚本入口 |
| --- | --- | --- | --- |
| `contracts` | 协议对象、字段、默认值、错误对象 | `tests/contracts/test_context_snapshot.py`<br>`tests/contracts/test_plan_refs.py`<br>`tests/contracts/test_guardrails_mapping.py`<br>`tests/contracts/test_tooling_contracts.py`<br>`tests/contracts/test_llm_contracts.py` | `./scripts/test_contracts.sh` |
| `runtime` | 状态机、追踪继承、回写时机 | `tests/runtime/test_state_transitions.py`<br>`tests/runtime/test_trace_inheritance.py`<br>`tests/runtime/test_writeback_timing.py` | `./scripts/test_runtime.sh` |
| `perception` | 单轮输入准备、桥接参数、草稿答案注入 | `tests/perception/test_round_preparation.py` | `./scripts/test_perception.sh` |
| `stm` | 持久化快照、写回记录、对话历史 | `tests/stm/test_persistence.py` | `./scripts/test_stm.sh` |
| `adapters` | `tool / mcp / llm` 归一、错误分支、配置读取 | `tests/adapters/test_adapters.py`<br>`tests/adapters/test_adapter_errors.py`<br>`tests/adapters/test_live_configuration.py` | `./scripts/test_adapters.sh` |
| `knowledge` | 知识库载体、`KB -> RAG` 链路与无结果边界 | `tests/knowledge/test_rag_adapter.py` | `./scripts/test_knowledge.sh` |
| `skills` | 目录扫描、frontmatter、资源清单与 `SKL_001 ~ SKL_003` | `tests/skills/test_skill_adapter.py` | `./scripts/test_skills.sh` |
| `orchestration` | `Planning / ReAct / Guardrails / Pipeline / REPL` 最小协作 | `tests/orchestration/test_pipeline.py`<br>`tests/orchestration/test_engines.py`<br>`tests/orchestration/test_repl_history.py` | `./scripts/test_orchestration.sh` |
| `integration` | CLI/Web 闭环、Web 会话恢复、澄清流与重置流 | `tests/integration/test_cli_roundtrip.py`<br>`tests/integration/test_web_roundtrip.py`<br>`tests/integration/test_web_session_resume.py`<br>`tests/integration/test_web_clarify_flow.py`<br>`tests/integration/test_web_session_controls.py` | `./scripts/test_integration.sh` |

### 11. 全量回归

执行：

```bash
./scripts/test_all.sh
```

或：

```bash
pytest tests/contracts tests/runtime tests/perception tests/stm tests/adapters tests/knowledge tests/skills tests/orchestration tests/integration
```

说明：

- `./scripts/test_all.sh` 固定执行顺序为：
  - `contracts`
  - `runtime`
  - `perception`
  - `stm`
  - `adapters`
  - `knowledge`
  - `skills`
  - `orchestration`
  - `integration`
- 当前默认回归共 `74` 项：
  - `contracts` 19
  - `runtime` 11
  - `perception` 6
  - `stm` 2
  - `adapters` 9
  - `knowledge` 4
  - `skills` 5
  - `orchestration` 9
  - `integration` 9
- `./scripts/test_all.sh` 默认不包含 `test_live_llm.sh` 与 `test_live_mcp.sh`

### 12. 真实联调测试

用途：

- 用于验证真实外部服务是否能接通。
- 只作为补充证据，不替代默认本地回归。
- 默认不属于阻断级门禁。

前置条件：

- 已完成本地安装：
  - `python -m pip install -e .`
- 已通过默认本地回归：
  - `./scripts/test_all.sh`
- 如需真实 LLM 联调，根目录需存在 `.env` 且至少包含：
  - `LLM_MODEL_ID`
  - `LLM_API_KEY`
  - `LLM_BASE_URL`
- 如需真实 MCP 联调，`pyproject.toml` 中目标 `mcp_servers.<name>` 必须可启动，且目标服务具备：
  - `tools/list`
  - `tools/call`
- 当前仓库预置的 `cunzhi` MCP 配置只适用于对应本地环境，换机后通常需要自行调整。

LLM 真实联调：

```bash
./scripts/test_live_llm.sh
```

MCP 配置联调：

```bash
./scripts/test_live_mcp.sh
```

使用约束：

- 不要把 `test_live_llm.sh` 或 `test_live_mcp.sh` 混入 `test_all.sh`。
- live 成功不能反向证明离线契约测试和边界测试已全部成立。
- live 失败时应先区分是环境问题还是代码问题，再决定是否回滚代码。

推荐判定顺序：

1. 先跑 `./scripts/test_all.sh`
2. 默认回归通过后，再跑 `./scripts/test_live_llm.sh`
3. 最后再跑 `./scripts/test_live_mcp.sh`

失败归因建议：

- 更可能是环境问题：
  - `.env` 缺失或字段不完整
  - `LLM_BASE_URL` 无法访问
  - API key 无效
  - MCP 可执行文件路径不存在
  - MCP 服务本身未启动或不支持标准能力
- 更可能是代码问题：
  - 默认本地回归已通过，但 live 请求参数明显构造错误
  - 响应归一字段缺失
  - `tool_calls / usage / provider_trace` 等协议字段映射异常
  - 相同环境下外部服务可手工访问，但脚本仍稳定失败

结果记录建议：

- 每次 live 联调至少记录：
  - 执行日期与执行人
  - 执行脚本：`test_live_llm.sh` 或 `test_live_mcp.sh`
  - 关键环境是否就绪：
    - `.env` 是否存在
    - `LLM_MODEL_ID / LLM_API_KEY / LLM_BASE_URL` 是否齐全
    - `mcp_servers.<name>` 是否可启动
  - 结果判定：成功 / 失败
  - 失败归因：环境问题 / 代码问题 / 待进一步确认
  - 后续动作：修环境、修代码或仅记录观察结论
- 如需对比多次联调，建议固定记录同一目标服务、同一脚本与同一配置来源，避免把环境漂移误判为代码回归。

## 使用演示

### 演示主链 `Pipeline`

这个脚本用于演示如何手工构造上下文、动作和执行上下文，并触发单轮主链：

```bash
python scripts/demo_pipeline.py --goal "搜索协议文档" --action-type tool --target search_docs
```

演示完成态：

```bash
python scripts/demo_pipeline.py --goal "整理结果" --action-type finish
```

脚本输出为单轮结果 JSON。

### 使用 CLI 入口

CLI 当前主要用于内部调试和最小兼容入口。

执行本地工具动作：

```bash
mz-agent --goal "搜索协议文档" --action-type tool --target search_docs
```

启用持久化 STM：

```bash
mz-agent --goal "搜索协议文档" --action-type tool --target search_docs --stm-path /tmp/mz-agent-stm.json
```

启用真实 LLM：

```bash
mz-agent --goal "请只回复：CLI_LIVE_OK" --action-type llm --live-llm --stm-path /tmp/mz-agent-live-stm.json
```

### 使用最小 REPL

启动本地样板 REPL：

```bash
mz-agent --repl
```

启动真实 LLM REPL：

```bash
mz-agent --repl --live-llm --stm-path /tmp/mz-agent-repl.json
```

REPL 内置命令：

```text
/help
/history
/status
/mode <动作类型>
/target <动作目标>
/reset
/exit
/quit
```

### 使用 Web 主入口

启动最小 Web 服务：

```bash
mz-agent-web --host 127.0.0.1 --port 8000
```

如需启用真实 LLM：

```bash
mz-agent-web --host 127.0.0.1 --port 8000 --live-llm --stm-path /tmp/mz-agent-web.json
```

首版页面能力：

- 任务配置：`goal / action_type / target / 发送 / 清空输入`
- 状态查看：状态标签、结果类型、历史条数、澄清原因
- 会话控制：复制会话、刷新状态、重置会话
- 会话视图：结果摘要区、历史列表、空态与错误提示

说明：

- 当前最小 REPL 默认使用 `llm` 动作。
- 当前最小 REPL 已支持切换到 `mcp` / `tool` 模式。
- 调用 `cunzhi` 的推荐方式：

```text
/mode mcp
/target cunzhi:zhi
直接输入要发送给 zhi 的文本
```

- 对话历史会写入 `ContextSnapshot.perception["conversation_messages"]`。
- 若配置了 `--stm-path`，历史会随 `FileBackedSTM` 一并持久化。

### 演示适配层

这个脚本用于按模块演示当前适配层如何返回标准化结果：

```bash
python scripts/demo_adapters.py --adapter tool
python scripts/demo_adapters.py --adapter mcp
python scripts/demo_adapters.py --adapter llm
python scripts/demo_adapters.py --adapter rag
python scripts/demo_adapters.py --adapter skill
```

启用真实 LLM：

```bash
python scripts/demo_adapters.py --adapter llm --live --prompt "请只回复：LIVE_OK"
```

列出 `cunzhi` MCP 能力：

```bash
python scripts/demo_adapters.py --adapter mcp --live --server cunzhi --list-capabilities
```

## 当前限制

- 当前 `LLMAdapter` 已支持从 `.env` 读取真实 OpenAI Compatible 配置并调用 Responses API。
- 当前 `MCPAdapter` 已支持从 `pyproject.toml` 读取 `stdio` MCP 服务配置，并对目标服务执行 `tools/list` / `tools/call`。
- 当前 `RAGAdapter` 使用内存块样板，不代表完整知识库检索链路。
- 当前 `SkillAdapter` 使用内存注册样板，不代表真实 Skill 目录装载。
- 当前 `Pipeline` 与 CLI 主要用于演示固定动作链/回答链、Guardrails 挂点和 STM 回写门禁。
- 当前最小 REPL 已支持持续输入和历史查看，但还不是完整 TUI。

## 后续路线

后续若继续扩展，优先方向应是：

- 更完整的配置与启动入口
- 更丰富的 REPL/TUI 交互能力
- 更完整的 MCP 结果归一与多服务路由
- 更细粒度的真实 provider 集成测试
- Skill 目录自动装载与真实知识库接入
- 更多细粒度模块测试与集成测试
