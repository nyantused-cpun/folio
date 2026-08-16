// @nyantused/folio-dsh-tools 工具定义表（纯数据 + 纯函数，零外部依赖，可独立单测）
//
// buildArgs 是纯函数：把模型传入的 typed args 映射为 CLI argv 片段。
// 命令形态契约：spawn 时拼在 [PYTHON, "_cli.py", ...] 之后，
// 必须满足 guard 的 CLI 白名单正则（python.exe _cli.py <args...>）。

export const TOOL_DEFS = [
  {
    name: "folio_status",
    description:
      "兰亭记忆面：所有客户状态一览（客户名/最近产出/待办/上下文新鲜度）。会话开始、切换客户、汇报进度时用。返回结构化 JSON。",
    parameters: {},
    buildArgs: () => ["status", "--json"],
    opts: { timeoutMs: 60000 },
  },
  {
    name: "folio_pending",
    description:
      "兰亭记忆面：扫描所有客户未完成待办。开工前查一次，避免漏事。返回文本清单。",
    parameters: {},
    buildArgs: () => ["pending"],
    opts: { timeoutMs: 60000 },
  },
  {
    name: "folio_recall",
    description:
      "兰亭记忆面：双路召回（BM25 关键词 + Embedding 语义）检索历史项目/材料/决策。问「之前做过类似的吗」「那个客户什么情况」时用。keywords 必填；指定 client 可按客户过滤（默认开启过滤）；跨客户搜索加 no_client_filter。返回结构化 JSON。",
    parameters: {
      keywords: {
        type: "array",
        items: { type: "string" },
        required: true,
        description: "检索关键词（1 到多个词）",
      },
      client: { type: "string", description: "客户名（用于别名展开与按客户过滤）" },
      rerank: { type: "boolean", description: "云端 LLM 精排（默认 false，走本地融合排序）" },
      no_client_filter: {
        type: "boolean",
        description: "禁用按客户过滤（跨客户搜索时用）",
      },
      no_embedding: { type: "boolean", description: "禁用 Embedding 语义召回（纯关键词）" },
    },
    buildArgs: (a) => [
      "recall",
      ...(Array.isArray(a.keywords) ? a.keywords : [String(a.keywords)]),
      ...(a.client ? ["--client", a.client] : []),
      ...(a.rerank ? ["--rerank"] : []),
      ...(a.no_embedding ? ["--no-embedding"] : []),
      ...(a.no_client_filter ? ["--no-client-filter"] : []),
      "--json",
    ],
    opts: { timeoutMs: 120000 },
  },
  {
    name: "folio_read",
    description:
      "兰亭记忆面：全文读取项目内文件（摘要 + 缓存）。读客户材料、历史方案、上下文档案时用；大文件自动走摘要链。参数是工作区内路径。",
    parameters: {
      file: { type: "string", required: true, description: "文件路径（工作区内）" },
    },
    buildArgs: (a) => ["read", a.file],
    opts: { timeoutMs: 120000 },
  },
  {
    name: "folio_chunk_read",
    description:
      "兰亭记忆面：按 path#anchor 读完整 chunk 全文（世界书/长文档切片阅读）。file_path 可带 #anchor 锚点（如 docs/PROJECT_DESIGN.md#主题守卫）。",
    parameters: {
      file_path: {
        type: "string",
        required: true,
        description: "文件路径（可带 #anchor 锚点）",
      },
    },
    buildArgs: (a) => ["chunk-read", a.file_path],
    opts: { timeoutMs: 60000 },
  },
  {
    name: "folio_graph_query",
    description:
      "兰亭记忆面：查询客户知识图谱（世界书）节点与边。client 必填；可按节点 ID/类型查，或查某节点的关联边。决策溯源、客户脉络梳理时用。返回结构化 JSON。",
    parameters: {
      client: { type: "string", required: true, description: "客户名" },
      node: { type: "string", description: "节点 ID" },
      type: {
        type: "string",
        enum: ["decision", "output", "insight", "method", "client_profile"],
        description: "节点类型过滤",
      },
      edges: { type: "string", description: "查询与该节点关联的边（传节点 ID）" },
    },
    buildArgs: (a) => [
      "graph-query",
      a.client,
      ...(a.node ? ["--node", a.node] : []),
      ...(a.type ? ["--type", a.type] : []),
      ...(a.edges ? ["--edges", a.edges] : []),
      "--json",
    ],
    opts: { timeoutMs: 60000 },
  },
  {
    name: "folio_session_start",
    description:
      "兰亭入口协议：会话开始——判层级 + 加载客户上下文 + 语义召回。新客户/新主题/压缩后必须调用；同客户连续对话可跳过。返回结构化 JSON（层级/上下文/召回结果）。",
    parameters: {
      user_input: { type: "string", required: true, description: "用户输入文本" },
      client: { type: "string", description: "客户名（必填，AGENTS.md 启动协议要求）" },
    },
    buildArgs: (a) => [
      "session-start",
      a.user_input,
      ...(a.client ? ["--client", a.client] : []),
      "--json",
    ],
    opts: { timeoutMs: 120000 },
  },
  {
    name: "folio_save",
    description:
      "兰亭会话结束协议：保存会话（写 task_history + context.md + graph/embedding 增量 + 合规检查）。会话收尾时调用；关键决策会随 save 归档。extra 四个键选填（--input= --decisions= --outputs= --pending=）。",
    parameters: {
      client: { type: "string", required: true, description: "客户名" },
      input: { type: "string", description: "本次会话输入要点" },
      decisions: { type: "string", description: "本次关键决策" },
      outputs: { type: "string", description: "本次产出路径（逗号分隔）" },
      pending: { type: "string", description: "遗留待办" },
    },
    buildArgs: (a) => [
      "save",
      a.client,
      ...(a.input ? [`--input=${a.input}`] : []),
      ...(a.decisions ? [`--decisions=${a.decisions}`] : []),
      ...(a.outputs ? [`--outputs=${a.outputs}`] : []),
      ...(a.pending ? [`--pending=${a.pending}`] : []),
    ],
    opts: { timeoutMs: 120000 },
  },
  {
    name: "folio_load",
    description:
      "兰亭记忆面：加载客户上下文（context.md + 决策 + 待办 + 索引摘要）。切入某客户工作时先调这个恢复记忆。返回文本。",
    parameters: {
      client: { type: "string", required: true, description: "客户名" },
    },
    buildArgs: (a) => ["load", a.client],
    opts: { timeoutMs: 60000 },
  },
  {
    name: "folio_verify",
    description:
      "兰亭质量面：验证生成产出的机械门禁（结构/密度/规范/合规）。每次产出后必须调用，PASS 才可交付；FAIL 会给出具体问题清单。",
    parameters: {
      file: { type: "string", required: true, description: "产出文件路径（HTML/PPTX/DOCX）" },
    },
    buildArgs: (a) => ["verify", a.file],
    opts: { timeoutMs: 120000 },
  },
  {
    name: "folio_review",
    description:
      "兰亭质量面：独立 LLM 会话审查产出质量（维度打分 + 问题清单）。adversarial=true 是挑刺者模式（只找问题不打分）；parallel=true 是 5 路并行各查一维。大件产出后与 verify 配合使用。",
    parameters: {
      output_file: { type: "string", required: true, description: "产出文件路径（HTML/PPT/DOCX）" },
      client: { type: "string", description: "客户名（加载铁律）" },
      spec: { type: "string", description: "spec.yml 路径（内容一致性检查）" },
      adversarial: { type: "boolean", description: "对抗性审查（挑刺者角色，只找问题）" },
      parallel: { type: "boolean", description: "并行审查（5 路独立会话各查一个维度）" },
    },
    buildArgs: (a) => [
      "review",
      a.output_file,
      ...(a.client ? ["--client", a.client] : []),
      ...(a.spec ? ["--spec", a.spec] : []),
      ...(a.adversarial ? ["--adversarial"] : []),
      ...(a.parallel ? ["--parallel"] : []),
    ],
    opts: { timeoutMs: 300000 },
  },
  {
    name: "folio_cite_audit",
    description:
      "兰亭质量面：引用审计——从 spec 提取引用 + 反向校验来源 + 主题覆盖检查。防幻觉铁律的机械执行者；交付前必跑。",
    parameters: {
      spec: { type: "string", required: true, description: "spec.yml 路径" },
      client: { type: "string", description: "客户名（主题守卫检查）" },
      output: { type: "string", description: "输出报告路径（须在 output/ 下；默认 spec 同名_审查报告.md）" },
    },
    buildArgs: (a) => [
      "cite-audit",
      a.spec,
      ...(a.client ? ["--client", a.client] : []),
      ...(a.output ? ["--output", a.output] : []),
    ],
    opts: { timeoutMs: 300000 },
  },
  {
    name: "folio_audit",
    description:
      "兰亭质量面：全系统审计（config=配置与命令面 / runtime=运行时守门 / behavior=行为 / theme=主题决策 / all=全量）。会话收尾兜底必跑 all；日常抽查可指定单项。",
    parameters: {
      mode: {
        type: "string",
        enum: ["config", "runtime", "behavior", "theme", "all"],
        description: "审计模式（默认由 CLI 决定，通常为 config）",
      },
      client: { type: "string", description: "客户名（mode=theme 时使用）" },
    },
    buildArgs: (a) => [
      "audit",
      ...(a.mode ? ["--mode", a.mode] : []),
      ...(a.client ? ["--client", a.client] : []),
    ],
    opts: { timeoutMs: 300000 },
  },
  {
    name: "folio_theme_verify",
    description:
      "兰亭质量面：检查产出文件是否覆盖客户 permanent 主题（铁律关键词）。生成后快速核对主题保真。",
    parameters: {
      file: { type: "string", required: true, description: "产出文件路径" },
      client: { type: "string", required: true, description: "客户名" },
    },
    buildArgs: (a) => ["theme-verify", a.file, a.client],
    opts: { timeoutMs: 120000 },
  },
  {
    name: "folio_spec_diff",
    description:
      "兰亭质量面：两份 spec.yml 结构化 diff（退出码 0=无差异 1=有差异 2=错误）。对比版本快照（.versions/ 下）看改了什么；评审 spec 变更时用。",
    parameters: {
      spec_a: { type: "string", required: true, description: "旧版 spec.yml 路径（对比基准）" },
      spec_b: { type: "string", required: true, description: "新版 spec.yml 路径" },
    },
    buildArgs: (a) => ["spec-diff", a.spec_a, a.spec_b],
    opts: { timeoutMs: 60000 },
  },
];
