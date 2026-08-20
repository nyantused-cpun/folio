# gewu-lanting · 格物兰亭 preset

本目录是格物（gewu）preset 扩展点的兰亭私有实例，托管于 Folio 仓库；格物公开仓库保持零耦合。

## 定位

把兰亭视觉规范 v3.0 要义与业务标记语义注入格物简报，让视觉子代理按兰亭的尺子审阅：

- 覆盖默认关注问题，替换为兰亭验收六项；
- 追加视觉规范要义段与业务标记语义段；
- 替换调度提示，固化 PPTX/HTML 渲染、分批读图、gewu_locate 核验流程。

preset 为纯数据对象，无副作用；契约与校验规则见格物开发计划 §2.2。

## 挂载方式
三选一即可，优先级：config presetPath > 环境变量 `GEWU_BRIEF_PRESET` > 内置 community preset。

### 1. 安装脚本（推荐）
```powershell
pwsh <workspace>/gewu/scripts/install-gewu-plugins.ps1 -Install -Preset "<workspace>/folio/plugins/gewu-lanting/brief-preset.js"
```

### 2. DSH 挂载 config
```yaml
- id: gewu-tools
  name: "<workspace>/.dsh/gewu-tools/index.js"
  config:
    presetPath: "<workspace>/folio/plugins/gewu-lanting/brief-preset.js"
```

### 3. 环境变量
```powershell
$env:GEWU_BRIEF_PRESET = "<workspace>/folio/plugins/gewu-lanting/brief-preset.js"
```

## 验证

| 检查项 | 预期结果 |
|---|---|
| 安装脚本 `-Verify` | 第四项显示 `PRESET_OK:lanting` |
| `gewu_prep` 返回 JSON | `preset` 字段为 `"lanting@3.0"` |
| `resolvePreset` 加载本文件 | `name` 为 `lanting`，`degraded` 为 `false` |
| 简报内容 | 含「视觉规范要义（兰亭 v3.0）」段与业务标记语义段 |

若预设加载失败，gewu 会降级到 community 并打 `preset_degraded` 标记，主流程不阻断；此时请检查路径、语法与契约长度。

## 规范来源指针

| 内容 | 来源 |
|---|---|
| 视觉规范 v3.0（双主题/版式/密度/图表） | `docs/dev_plan_visual_v3_2026-08-11.md` |
| 三态色 D-092 | `decisions.md` |
| 实测坑位（⭐/虚线框/带色块数字） | `gewu/docs/TESTING.md` |
| 调度 SOP（分批/核验/交叉核实） | `<workspace>/.agents/skills/vision-review/SKILL.md（发布版 skills 挂载目录）` |

## 变更纪律

- 兰亭视觉规范升级时同步 bump `brief-preset.js` 的 `version`（当前 v3.0 → `"3.0"`）；
- 每次版本变更在 `folio/CHANGELOG.md` 记录；
- 不得向 gewu 公开仓库提交本目录任何内容。