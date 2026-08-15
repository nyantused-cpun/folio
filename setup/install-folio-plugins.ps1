# install-folio-plugins：@folio/dsh-tools + @folio/dsh-events 一键安装/卸载/验证
# （P1 装配，2026-08-14；对齐 presales-setup 工程标准：原子写 + 锁 + 幂等 + 卸载还原）
#
# 用法：
#   pwsh .dsh\setup\install-folio-plugins.ps1 -Install   # 安装（Junction + patch 行，幂等）
#   pwsh .dsh\setup\install-folio-plugins.ps1 -Verify    # 只验证不落盘
#   pwsh .dsh\setup\install-folio-plugins.ps1 -Uninstall # 删 Junction + 还原 patch
#   pwsh .dsh\setup\install-folio-plugins.ps1 -DryRun    # 报告计划不执行
#
# 安装后必须重启 dsh web 才生效（host 插件无 HMR）。
# 退出码：0 = 成功或用户取消（DryRun/跳过）；1 = 任何失败。

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Verify,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projRoot = Split-Path -Parent $scriptRoot   # 发布版：脚本在 folio/setup/ 下，projRoot = folio 仓库根
$dshHome = Join-Path $env:USERPROFILE ".dsh"
$profileNodeModules = Join-Path $dshHome "profiles\web\node_modules"
$folioScopeDir = Join-Path $profileNodeModules "@folio"
$patchPath = Join-Path $dshHome "profiles\web\cordis.patch.yml"
$patchBak = Join-Path $dshHome "profiles\web\cordis.patch.yml.bak-folio"
$lockPath = Join-Path $dshHome ".folio-plugins-install.lock"

$plugins = @(
    @{ Id = "folio-tools"; Name = "@folio/dsh-tools"; Src = Join-Path $projRoot "plugins\folio-tools" },
    @{ Id = "folio-events"; Name = "@folio/dsh-events"; Src = Join-Path $projRoot "plugins\folio-events" }
)

function Write-Step([string]$msg) { Write-Host "  $msg" }

function Get-PatchEntryLines {
    return @(
        "  # ── 兰亭（Folio）P1 插件层（install-folio-plugins.ps1 维护）──────────────────",
        "  - insert:",
        "      - id: folio-tools",
        '        name: "@folio/dsh-tools"',
        "        config: {}",
        "      - id: folio-events",
        '        name: "@folio/dsh-events"',
        "        config: {}"
    )
}

function Test-Junctions {
    foreach ($p in $plugins) {
        $link = Join-Path $folioScopeDir $p.Id
        if (-not (Test-Path $link)) { return $false }
        $item = Get-Item $link -Force
        if ($item.LinkType -ne "Junction") { return $false }
    }
    return $true
}

function Test-PatchLines {
    if (-not (Test-Path $patchPath)) { return $false }
    $content = Get-Content $patchPath -Raw -Encoding UTF8
    return $content.Contains('name: "@folio/dsh-tools"') -and $content.Contains('name: "@folio/dsh-events"')
}

function Test-Installed {
    return (Test-Junctions) -and (Test-PatchLines)
}

function Write-AtomicText([string]$path, [string]$content) {
    $tmp = "$path.tmp.$([guid]::NewGuid().ToString('N').Substring(0,8))"
    Set-Content -Path $tmp -Value $content -Encoding UTF8 -NoNewline
    Move-Item -Path $tmp -Destination $path -Force
}

function Invoke-InstallPlan {
    if (Test-Installed) { Write-Step "已安装且一致（幂等跳过）"; return $false }
    if (-not (Test-Junctions)) { Write-Step "计划：建 @folio Junction x2（$folioScopeDir）" }
    if (-not (Test-PatchLines)) { Write-Step "计划：cordis.patch.yml 追加 folio-tools/folio-events insert（先备份 $patchBak）" }
    if ($DryRun) { Write-Step "[DryRun] 不落盘"; return $false }
    return $true
}

try {
    if (Test-Path $lockPath) {
        $lockAge = (Get-Date) - (Get-Item $lockPath).LastWriteTime
        if ($lockAge.TotalMinutes -lt 10) {
            Write-Host "另一 setup 实例运行中（锁存在），本次跳过。"; exit 0
        }
        Remove-Item $lockPath -Force
    }
    Set-Content -Path $lockPath -Value "locked" -Encoding UTF8

    if ($Verify) {
        Write-Host "== folio 插件安装验证 =="
        $ok = $true
        foreach ($p in $plugins) {
            $link = Join-Path $folioScopeDir $p.Id
            $junctionOk = (Test-Path $link) -and ((Get-Item $link -Force).LinkType -eq "Junction")
            Write-Host ("  [Junction] {0} -> {1}  {2}" -f $link, $p.Src, $(if ($junctionOk) { "OK" } else { "MISSING" }))
            if (-not $junctionOk) { $ok = $false }
            if (Test-Path (Join-Path $p.Src "index.js")) {
                $err = node --check (Join-Path $p.Src "index.js") 2>&1
                if ($LASTEXITCODE -ne 0) { Write-Host "  [Syntax] $($p.Id) FAIL: $err"; $ok = $false }
                else { Write-Host "  [Syntax] $($p.Id) OK" }
            } else { Write-Host "  [Syntax] $($p.Id) MISSING index.js"; $ok = $false }
        }
        Write-Host ("  [Patch] cordis.patch.yml 含两行 insert  {0}" -f $(if (Test-PatchLines) { "OK" } else { "MISSING" }))
        if (-not (Test-PatchLines)) { $ok = $false }
        Write-Host ("验证结果: {0}" -f $(if ($ok) { "PASS（重启 dsh web 后生效）" } else { "FAIL" }))
        exit $(if ($ok) { 0 } else { 1 })
    }

    if ($Uninstall) {
        Write-Host "== folio 插件卸载 =="
        foreach ($p in $plugins) {
            $link = Join-Path $folioScopeDir $p.Id
            if (Test-Path $link) { Remove-Item $link -Force -Recurse; Write-Step "删 Junction: $($p.Id)" }
        }
        $dir = Get-ChildItem $folioScopeDir -Force -ErrorAction SilentlyContinue
        if (-not $dir) { Remove-Item $folioScopeDir -Force }
        if (Test-Path $patchBak) {
            Copy-Item $patchBak $patchPath -Force
            Write-Step "还原 cordis.patch.yml（自备份）"
        } else {
            Write-Step "无备份可还原（请手工删 patch 中 folio insert 段）"
        }
        Write-Host "卸载完成。"
        exit 0
    }

    if ($Install -or $DryRun) {
        Write-Host "== folio 插件安装 =="
        if (-not (Invoke-InstallPlan)) { exit 0 }
        # 1. Junctions
        if (-not (Test-Junctions)) {
            New-Item -ItemType Directory -Path $folioScopeDir -Force | Out-Null
            foreach ($p in $plugins) {
                $link = Join-Path $folioScopeDir $p.Id
                if (Test-Path $link) { Remove-Item $link -Force -Recurse }
                New-Item -ItemType Junction -Path $link -Target $p.Src | Out-Null
                Write-Step "Junction: $($p.Id) -> $($p.Src)"
            }
        }
        # 2. patch 行（原子写 + 备份）
        if (-not (Test-PatchLines)) {
            $content = Get-Content $patchPath -Raw -Encoding UTF8
            if (-not (Test-Path $patchBak)) { Copy-Item $patchPath $patchBak -Force }
            $entry = (Get-PatchEntryLines) -join "`r`n"
            $content = $content.TrimEnd() + "`r`n" + $entry + "`r`n"
            Write-AtomicText $patchPath $content
            Write-Step "cordis.patch.yml 已追加 insert 段（备份: $patchBak）"
        }
        Write-Host "安装完成。**重启 dsh web 后生效**（host 插件无 HMR）。"
        exit 0
    }

    Write-Host "无操作。用法见脚本头部注释（-Install/-Verify/-Uninstall/-DryRun）。"
    exit 0
}
finally {
    if (Test-Path $lockPath) { Remove-Item $lockPath -Force }
}
