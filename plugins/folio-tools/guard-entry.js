// @nyantused/folio-dsh-tools/guard —— L0 守卫插件入口（原 @presales/dsh-guard 合并，2026-08-16）
//
// 为什么是子入口而不是并进主入口：
// - 主入口 @nyantused/folio-dsh-tools 按脚本拓扑挂在 pre-sales preset 层（工具限售前模式）；
// - L0 守卫必须挂 profile 层（fs/write-intent 从 root scope 发出，preset 内监听不到）；
// - 因此同一个包内拆两个 entry：preset 层挂主入口，profile 层挂本子入口。
// 对 awesome-dsh-plugin / dshmarket 而言，仍是同一个仓库/包 `@nyantused/folio-dsh-tools`，
// 不需要为守卫单独提交 PR。

import { createGuardRules } from "./guard.js";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const name = "folio-guard";
const inject = ["tools"];

// 与主入口共用同一套 Folio 安装根解析（env 优先，其次从本包位置向上找 _cli.py，最后 cwd）。
function resolveProjectDir() {
  if (process.env.FOLIO_HOME) return process.env.FOLIO_HOME;
  if (process.env.DSH_PROJECT_DIR) return process.env.DSH_PROJECT_DIR;
  if (process.env.PRESALES_PROJECT_DIR) return process.env.PRESALES_PROJECT_DIR;
  try {
    let dir = dirname(fileURLToPath(import.meta.url));
    for (let i = 0; i < 5; i++) {
      if (existsSync(resolve(dir, "_cli.py"))) return dir;
      dir = dirname(dir);
    }
  } catch { /* noop */ }
  return process.cwd();
}

const PROJECT_DIR = resolveProjectDir();

function apply(ctx) {
  createGuardRules(PROJECT_DIR).install(ctx);
}

export { apply, inject, name };
