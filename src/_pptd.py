# -*- coding: utf-8 -*-
"""pptd 富媒体 PPT 构建：backend 抽象 + python-pptx 转换 + COM 截图目检。

背景：pptd 路线是富媒体 PPT 的既定方向。原封装对象 kimi_ppt_dsl.pyz 已随
Kimi Desktop 更新永久删除（D-088/C-1 实测），替代路线经 2026-08-12 决策
改为**自研 python-pptx 转换器**（保留 v1 pptd 方言，只换转换后端）。

本模块职责：
- backend 抽象（PptxBackend）：check / convert 两个能力，`PPTD_BACKEND`
  环境变量选择实现（当前唯一实现 python_pptx，见 _pptd_convert.py）
- 引擎无关的通用能力：COM 截图目检（export_shots）、五类 Warning 统计、
  check_report.json 落盘

决策依据：docs/材料生成管线C1_方言迁移差异清单_2026-08-12.md
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

# 备选的 pwsh 绝对路径（PATH 找不到 pwsh 时用）
_PWSH_FALLBACKS = [
    r"C:\Program Files\PowerShell\7\pwsh.exe",
]

# COM 逐页导出 PNG 的 PowerShell 脚本（运行期写入 ASCII 临时目录，用完即删）。
# 单文件版，源自 .audit/export_ppt5.ps1。
_EXPORT_PS1 = r"""
param(
    [Parameter(Mandatory=$true)][string]$Pptx,
    [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ppt = $null
$pres = $null
try {
    $ppt = New-Object -ComObject "PowerPoint.Application"
} catch {
    Write-Host ("Cannot launch PowerPoint: " + $_)
    exit 1
}
try {
    # Open(FileName, ReadOnly=0, Untitled=0, WithWindow=0) 无窗打开
    $pres = $ppt.Presentations.Open($Pptx, 0, 0, 0)
    $count = 1
    foreach ($slide in $pres.Slides) {
        $pngPath = [System.IO.Path]::Combine($OutDir, ("slide_{0:D2}.png" -f $count))
        $slide.Export($pngPath, "PNG", 1280, 720)
        $count++
    }
    Write-Host ("Exported " + ($count - 1) + " slides")
} catch {
    Write-Host ("Export failed: " + $_)
    exit 1
} finally {
    if ($pres -ne $null) { try { $pres.Close() } catch {} }
    if ($ppt -ne $null) {
        try { $ppt.Quit() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
    }
    [System.GC]::Collect()
}
"""


# ---------------------------------------------------------------------------
# backend 抽象（可插拔引擎，2026-08-12 起唯一实现为 python_pptx）
# ---------------------------------------------------------------------------
class PptxBackend:
    """PPT 转换后端抽象：pptd 工程 -> 校验 / PPTX 转换。

    接口语义（对调用方 _cli_generate 恒定，C-2 验收要求）：
    - check(pptd_path) -> (ok: bool, warn_counts: dict)
    - convert(pptd_path, out_path) -> bool
    """

    name = "base"

    def check(self, pptd_path):
        """校验 pptd 工程。error 阻断、warning 放行，返回 (ok, 五类 warning 计数)。"""
        raise NotImplementedError

    def convert(self, pptd_path, out_path):
        """把 pptd 工程转换为 PPTX。成功返回 True。"""
        raise NotImplementedError


class PythonPptxBackend(PptxBackend):
    """自研转换后端：python-pptx 把 v1 pptd 工程转成 PPTX（C-3 实现）。

    不依赖任何外部可执行文件，链路口径完全自控。
    """

    name = "python_pptx"

    def check(self, pptd_path):
        from _pptd_convert import check_pptd
        return check_pptd(pptd_path)

    def convert(self, pptd_path, out_path):
        from _pptd_convert import convert_pptd
        return convert_pptd(pptd_path, out_path)


def get_backend():
    """按 PPTD_BACKEND 环境变量选择后端实例；未知名称给中文报错返回 None。

    未设置时默认 python_pptx（pyz 已死，无保留价值）。
    """
    name = os.environ.get("PPTD_BACKEND", "python_pptx").strip().lower()
    if name == "python_pptx":
        return PythonPptxBackend()
    print(f"[阻断] 未知 PPTD_BACKEND: {name}（当前支持: python_pptx）")
    return None


def get_backend_or_exit():
    """同 get_backend，但后端不可用（含 python-pptx 依赖缺失）时中文报错退出。

    供命令层调用；保证不 traceback、报错含环境变量提示。
    """
    backend = get_backend()
    if backend is None:
        sys.exit(1)
    try:
        import pptx  # noqa: F401
    except ImportError:
        print("[阻断] 缺少 python-pptx 依赖（转换后端必需），请安装：")
        print("  ./.venv/Scripts/python.exe -m pip install python-pptx")
        sys.exit(1)
    return backend


# ---------------------------------------------------------------------------
# 版式维五类 Warning（§10 检查 7，单点定义；_verify.py 复检消费）
# ---------------------------------------------------------------------------
PPTD_WARN_TYPES = ("TextOverflow", "TextOcclusion", "TextDrift",
                   "TextUnderfill", "BoundsOutside")


def parse_check_warnings(text):
    """从 check 输出统计版式维五类 Warning（§10 检查 7）。

    返回 {类型: 次数}，只含五类（TextOverflow/TextOcclusion/TextDrift/
    TextUnderfill/BoundsOutside）；其他 warning 不计入。
    """
    counts = {}
    for t in PPTD_WARN_TYPES:
        n = len(re.findall(re.escape(t), text or ""))
        if n:
            counts[t] = n
    return counts


def write_check_report(pptd_path, warn_counts):
    """五类 warning 计数写工程目录 check_report.json（verify 检查 7 消费）。"""
    import json
    deck_dir = os.path.dirname(os.path.abspath(pptd_path)) or "."
    path = os.path.join(deck_dir, "check_report.json")
    payload = {"pptd": os.path.basename(pptd_path), "warnings": warn_counts}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    total = sum(warn_counts.values())
    if total:
        detail = ", ".join(f"{t}×{n}" for t, n in sorted(warn_counts.items()))
        print(f"[check] 版式维五类 Warning 待处理（§10 检查 7）：{detail}"
              f"（已记录 {path}，verify 将判 error）")
    return path


# ---------------------------------------------------------------------------
# COM 截图（引擎无关；目检依赖本机 PowerPoint，与转换后端解耦）
# ---------------------------------------------------------------------------
def find_pwsh():
    """定位 PowerShell 解释器：PATH 的 pwsh -> 备选绝对路径 -> PATH 的 powershell。"""
    exe = shutil.which("pwsh")
    if exe:
        return exe
    for cand in _PWSH_FALLBACKS:
        if os.path.exists(cand):
            return cand
    return shutil.which("powershell")


def default_shots_dir(pptx_path):
    """截图默认输出目录：<pptx 所在目录>/_shots_<pptx 名>/"""
    base = os.path.splitext(os.path.basename(pptx_path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(pptx_path)), f"_shots_{base}")


def export_shots(pptx_path, out_dir):
    """COM 逐页导出 PNG 截图（1280x720），供目检。

    中文路径处理：pptx 先复制到 ASCII 临时目录再导出（COM Export 对
    中文路径不稳定，v3 实战踩过），PNG 回收后清理临时目录。
    """
    pwsh = find_pwsh()
    if not pwsh:
        print("[截图] 未找到 pwsh/powershell，无法导出截图")
        return False
    os.makedirs(out_dir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="pptd_shots_")
    try:
        ascii_pptx = os.path.join(tmp, "deck.pptx")
        ascii_png = os.path.join(tmp, "png")
        ps1_path = os.path.join(tmp, "export.ps1")
        shutil.copy2(pptx_path, ascii_pptx)
        with open(ps1_path, "w", encoding="utf-8") as f:
            f.write(_EXPORT_PS1)

        proc = subprocess.run(
            [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", ps1_path, "-Pptx", ascii_pptx, "-OutDir", ascii_png],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if out.strip():
            print(out.rstrip())
        if proc.returncode != 0:
            print("[截图] COM 导出失败（本机是否安装了 PowerPoint？）")
            return False

        moved = 0
        if os.path.isdir(ascii_png):
            for name in sorted(os.listdir(ascii_png)):
                if name.lower().endswith(".png"):
                    shutil.move(os.path.join(ascii_png, name),
                                os.path.join(out_dir, name))
                    moved += 1
        if moved == 0:
            print("[截图] 未导出任何 PNG")
            return False
        print(f"[截图] 已导出 {moved} 页 PNG -> {out_dir}")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
