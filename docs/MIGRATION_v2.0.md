# Folio v2.0 迁移指南（v1.x → v2.0.0）

> v2.0.0 是同源对齐大版本。绝大多数用户**零改动升级**；只用了旧 `style` 字段
> 或 `insight`/`feedback`/`skill` 命令的用户需要按本指南迁移。
> 配套文档：[技术白皮书 v6.0](兰亭_技术白皮书_v6.0.md) / [产品说明 v6.0](兰亭_产品说明_v6.0.md)。

## 1. 主题体系并轨（唯一影响 spec 外观的变更）

v2.0 把旧 `style` 双轨迁到统一主题令牌体系。你的 spec 里如果写了：

```yaml
style: enterprise   # v1.x
```

v2.0 起 **自动映射**，无需必改：

| v1.x style | v2.0 主题 | 视觉 |
|---|---|---|
| `enterprise` | `corporate_navy` | 企业藏青（新默认族） |
| `tech` | `product_charcoal` | 深编辑蓝+暖纸底 |
| `education` | `consulting_kpmg` | KPMG 咨询风（新默认） |
| `gov` | `gov_red` | 政务红 |
| `syzygit` | `syzygit` | VI 主题（收编为正式主题） |

加载时会在输出里打印 `[主题迁移]` 提示。想消除提示：把 spec 里的 `style:`
直接改成上表右列的主题名。未写 `style` 的 spec 默认主题视觉与 v1.x 有差异
（旧 enterprise → consulting_kpmg 咨询风），如需还原旧观感请显式写
`style: corporate_navy`。

## 2. 下线命令

| v1.x 命令 | 状态 | 替代 |
|---|---|---|
| `insight` | 下线 | 会话洞察并入 `save` 链 |
| `feedback` | 下线 | review 链覆盖其职责 |
| `skill` | 下线 | `skills-sync` / `load-skill` |

## 3. spec 协议对齐

v1.x 的社区 spec 与内部 spec 存在分叉（渲染契约不同）。v2.0 起两端口径一致：
- `narrative_schema`（叙事单）与 37 种 diagram subtype 全量可用；
- v1.x 能渲染的 spec 在 v2.0 仍能渲染（增字段向后兼容），但**视觉输出**可能
  随主题体系变化（见 §1）。

## 4. 其他变化

- 命令面 65 → 87（新增 breed/audit 观测面/review 增强旗标等，全部向后兼容）。
- `_knowledge/` 知识目录新增 domains/cases/methodology 示例卡（虚构示例数据）。
- 测试面 69 → 191 个文件（发布文案）/ 192（仓库实测）；CI 不变（pytest）。
- DSH 兼容：发布版锚定 0.1.0-rc.8；0.1.2-rc.1 代码级兼容层随下一版同步。

## 5. 升级步骤

```powershell
git pull
.\setup\install.ps1   # 重跑安装（增量装依赖）
python _cli.py audit --mode config   # 自检配置面
```
