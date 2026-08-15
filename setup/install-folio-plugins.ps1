# install-folio-plugins：presales-guard + folio-tools + folio-events 一键安装/卸载/验证
# （P1 装配，2026-08-14；作用域隔离拓扑 2026-08-15；v1.0.1 发布版）
#
# 拓扑（2026-08-15 作用域隔离修复，解决「兰亭全局污染其他项目」）：
#   - folio-tools / folio-events → 挂载于 pre-sales preset
#     （~/.dsh/.agent-presets/pre-sales/agent.cordis.yml，绝对路径引用本仓库
#     plugins/ 下的 index.js）：仅「售前助手」模式会话生效，其他项目零污染。
#   - presales-guard → 保持 profile 全局（fs/write-intent 事件从 root scope 发出，
#     preset 内监听不到，L0 防线不能进 preset）；拦截逻辑已加项目内自检
#     （guard/index.js isCommandInProject），非售前项目完全放行。
#   - vision-bridge → 未随开源分发（内部能力），需要时自备并手工在 preset 补一行；
#     本脚本不管理它，也不会为它建 Junction。
#
# 用法：
#   pwsh .\setup\install-folio-plugins.ps1 -Install   # 安装（幂等）
#   pwsh .\setup\install-folio-plugins.ps1 -Verify    # 只验证不落盘
#   pwsh .\setup\install-folio-plugins.ps1 -Uninstall # 清理（还原两处 patch + 删 Junction）
#   pwsh .\setup\install-folio-plugins.ps1 -DryRun    # 报告计划不执行
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
$projRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
$dshHome = Join-Path $env:USERPROFILE ".dsh"
$profileNodeModules = Join-Path $dshHome "profiles\web\node_modules"
$presalesScopeDir = Join-Path $profileNodeModules "@presales"
$folioScopeDir = Join-Path $profileNodeModules "@folio"
$patchPath = Join-Path $dshHome "profiles\web\cordis.patch.yml"
$patchBak = Join-Path $dshHome "profiles\web\cordis.patch.yml.bak-folio"
# preset 挂载点（2026-08-15 起，folio 两插件）
$presetFile = Join-Path $dshHome ".agent-presets\pre-sales\agent.cordis.yml"
$presetBak = Join-Path $dshHome ".agent-presets\pre-sales\agent.cordis.yml.bak-folio"
# 全新 preset 模板（发布仓库自带；已存在时不覆盖，只追加插件行）
$presetSource = Join-Path $projRoot "preset\agent.cordis.yml"
$lockPath = Join-Path $dshHome ".folio-plugins-install.lock"
# @deepseek-ai 解析桥：preset 插件经 file URL 直指本仓库 plugins/ 后，
# import '@deepseek-ai/*' 需从 $projRoot\node_modules 向上解析（2026-08-15 实测修复）。
$dshAiLink = Join-Path $projRoot "node_modules\@deepseek-ai"

# 路径转 file URL 风格（正斜杠；PresetTree.import 对绝对路径转 file URL）
function ConvertTo-Fwd([string]$p) { return ($p -replace "\\", "/") }

# guard：profile 层（Junction 包名解析）。Link 必须与包名 scope 后段一致。
$guardPlugin = @{ Id = "presales-guard"; Name = "@presales/dsh-guard"; Link = "dsh-guard"; ScopeDir = $presalesScopeDir; Src = Join-Path $projRoot "guard" }
# folio 两插件：preset 层（绝对路径引用，无需 Junction）
$presetPlugins = @(
    @{ Id = "folio-tools";  Src = Join-Path $projRoot "plugins\folio-tools" },
    @{ Id = "folio-events"; Src = Join-Path $projRoot "plugins\folio-events" }
)
# 旧拓扑残留（2026-08-15 前的 Junction，安装/卸载时清理；含历史版本两种命名）
$legacyLinks = @(
    @{ Dir = $folioScopeDir; Link = "dsh-tools" },
    @{ Dir = $folioScopeDir; Link = "dsh-events" },
    @{ Dir = $folioScopeDir; Link = "folio-tools" },
    @{ Dir = $folioScopeDir; Link = "folio-events" },
    @{ Dir = $presalesScopeDir; Link = "dsh-vision-bridge" },
    @{ Dir = $presalesScopeDir; Link = "vision-bridge" }
)

function Write-Step([string]$msg) { Write-Host "  $msg" }

# 探测 dsh 运行时的 @deepseek-ai 目录（从 dsh.ps1 位置推导，路径随 node 版本变化）
function Get-DshAiTarget {
    $cmd = Get-Command dsh -ErrorAction SilentlyContinue
    if (-not $cmd -or -not $cmd.Source) { return $null }
    $dshRoot = Split-Path $cmd.Source
    $candidate = Join-Path $dshRoot "node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai"
    if (-not (Test-Path (Join-Path $candidate "dsh-tools\package.json"))) { return $null }
    return $candidate
}

function Test-AiBridge {
    if (-not (Test-Path $dshAiLink)) { return $false }
    $item = Get-Item $dshAiLink -Force
    return $item.LinkType -eq "Junction"
}

function Get-ProfilePatchLines {
    # guard 保持 profile 全局（root scope 事件监听，L0 防线）
    return @(
        "# presales-guard（Folio L0 守卫，D-127）：拦 output/refs 直写 + 非 CLI python 直调。",
        "# 2026-08-15 作用域隔离：仅对售前项目内命令生效（guard/index.js isCommandInProject）。",
        "- insert:",
        "    - id: presales-guard",
        '      name: "@presales/dsh-guard"',
        "      config: {}"
    )
}

function Get-PresetLines {
    # folio 两插件挂 pre-sales preset。绝对路径必须指向 index.js 文件——
    # Node ESM 不支持目录导入（2026-08-15 实测 ERR_UNSUPPORTED_DIR_IMPORT）；
    # PresetTree.import 对绝对路径转 file URL（官方支持盘符路径）。
    $rootFwd = ConvertTo-Fwd $projRoot
    return @(
        "",
        "# ── 兰亭（Folio）P1 插件层（install-folio-plugins.ps1 维护；2026-08-15 从 profile",
        "#    全局层迁入本 preset——仅「售前助手」模式生效，其他项目零污染）─────────────",
        "- id: folio-tools",
        "  name: `"$rootFwd/plugins/folio-tools/index.js`"",
        "  config: {}",
        "- id: folio-events",
        "  name: `"$rootFwd/plugins/folio-events/index.js`"",
        "  config: {}"
    )
}

function Test-GuardJunction {
    $link = Join-Path $guardPlugin.ScopeDir $guardPlugin.Link
    if (-not (Test-Path $link)) { return $false }
    $item = Get-Item $link -Force
    return $item.LinkType -eq "Junction"
}

function Test-ProfilePatchLines {
    if (-not (Test-Path $patchPath)) { return $false }
    $content = Get-Content $patchPath -Raw -Encoding UTF8
    return $content.Contains('name: "@presales/dsh-guard"')
}

function Test-PresetLines {
    if (-not (Test-Path $presetFile)) { return $false }
    $content = Get-Content $presetFile -Raw -Encoding UTF8
    $rootFwd = ConvertTo-Fwd $projRoot
    return $content.Contains("$rootFwd/plugins/folio-tools/index.js") -and
           $content.Contains("$rootFwd/plugins/folio-events/index.js")
}

function Test-NoLegacyJunctions {
    foreach ($l in $legacyLinks) {
        if (Test-Path (Join-Path $l.Dir $l.Link)) { return $false }
    }
    return $true
}

function Test-Installed {
    return (Test-GuardJunction) -and (Test-ProfilePatchLines) -and (Test-PresetLines) -and (Test-NoLegacyJunctions)
}

function Remove-LegacyJunctions {
    foreach ($l in $legacyLinks) {
        $link = Join-Path $l.Dir $l.Link
        if (Test-Path $link) { Remove-Item $link -Force -Recurse; Write-Step "清理旧 Junction: $($l.Link)" }
    }
}

function Write-AtomicText([string]$path, [string]$content) {
    $tmp = "$path.tmp.$([guid]::NewGuid().ToString('N').Substring(0,8))"
    Set-Content -Path $tmp -Value $content -Encoding UTF8 -NoNewline
    Move-Item -Path $tmp -Destination $path -Force
}

function Invoke-InstallPlan {
    if (Test-Installed -and (Test-AiBridge)) { Write-Step "已安装且一致（幂等跳过）"; return $false }
    if (-not (Test-GuardJunction)) { Write-Step "计划：建 guard Junction（$presalesScopeDir\dsh-guard）" }
    if (-not (Test-AiBridge)) { Write-Step "计划：建 @deepseek-ai 解析桥（$dshAiLink）" }
    if (-not (Test-ProfilePatchLines)) { Write-Step "计划：cordis.patch.yml 追加 guard insert（先备份 $patchBak）" }
    if (-not (Test-PresetLines)) { Write-Step "计划：pre-sales preset 追加 folio 两插件行（先备份 $presetBak）" }
    if (-not (Test-NoLegacyJunctions)) { Write-Step "计划：清理旧拓扑 Junction（@folio / @presales/dsh-vision-bridge）" }
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
        Write-Host "== 兰亭生态插件安装验证（作用域隔离拓扑）=="
        $ok = $true
        # guard（profile 层）
        $gLink = Join-Path $guardPlugin.ScopeDir $guardPlugin.Link
        $gJunctionOk = (Test-Path $gLink) -and ((Get-Item $gLink -Force).LinkType -eq "Junction")
        Write-Host ("  [Junction] guard {0}  {1}" -f $gLink, $(if ($gJunctionOk) { "OK" } else { "MISSING" }))
        if (-not $gJunctionOk) { $ok = $false }
        # folio 两插件（preset 层，语法检查）
        foreach ($p in $presetPlugins) {
            if (Test-Path (Join-Path $p.Src "index.js")) {
                $err = node --check (Join-Path $p.Src "index.js") 2>&1
                if ($LASTEXITCODE -ne 0) { Write-Host "  [Syntax] $($p.Id) FAIL: $err"; $ok = $false }
                else { Write-Host "  [Syntax] $($p.Id) OK" }
            } else { Write-Host "  [Syntax] $($p.Id) MISSING index.js"; $ok = $false }
        }
        Write-Host ("  [AiBridge] @deepseek-ai 解析桥  {0}" -f $(if (Test-AiBridge) { "OK" } else { "MISSING" }))
        if (-not (Test-AiBridge)) { $ok = $false }
        Write-Host ("  [Patch] profile guard insert  {0}" -f $(if (Test-ProfilePatchLines) { "OK" } else { "MISSING" }))
        if (-not (Test-ProfilePatchLines)) { $ok = $false }
        Write-Host ("  [Patch] preset folio 两插件行  {0}" -f $(if (Test-PresetLines) { "OK" } else { "MISSING" }))
        if (-not (Test-PresetLines)) { $ok = $false }
        # import 冒烟：guard 走包名（profile 解析）；preset 插件走 file URL 直指 index.js
        $smokeOk = $true
        Push-Location (Split-Path $profileNodeModules)
        $smokeGuard = node --input-type=module -e "await import('@presales/dsh-guard')" 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Host "  [Import] guard FAIL: $smokeGuard"; $smokeOk = $false } else { Write-Host "  [Import] guard OK" }
        Pop-Location
        foreach ($p in $presetPlugins) {
            $url = "file:///" + ((ConvertTo-Fwd $p.Src) + "/index.js" -replace " ", "%20")
            $r = node --input-type=module -e "await import('$url')" 2>&1
            if ($LASTEXITCODE -ne 0) { Write-Host "  [Import] $($p.Id) FAIL: $r"; $smokeOk = $false } else { Write-Host "  [Import] $($p.Id) OK" }
        }
        if (-not $smokeOk) { $ok = $false }
        Write-Host ("验证结果: {0}" -f $(if ($ok) { "PASS（重启 dsh web 后生效）" } else { "FAIL" }))
        exit $(if ($ok) { 0 } else { 1 })
    }

    if ($Uninstall) {
        Write-Host "== 兰亭生态插件卸载 =="
        # guard Junction + profile patch 还原
        $gLink = Join-Path $guardPlugin.ScopeDir $guardPlugin.Link
        if (Test-Path $gLink) { Remove-Item $gLink -Force -Recurse; Write-Step "删 guard Junction" }
        if (Test-Path $patchBak) {
            Copy-Item $patchBak $patchPath -Force
            Write-Step "还原 cordis.patch.yml（自备份）"
        } else {
            Write-Step "无备份可还原（请手工删 patch 中 guard insert 段）"
        }
        # preset 行还原
        if (Test-Path $presetBak) {
            Copy-Item $presetBak $presetFile -Force
            Write-Step "还原 pre-sales preset（自备份）"
        } else {
            Write-Step "无 preset 备份可还原（请手工删 preset 中 folio 两插件行）"
        }
        Remove-LegacyJunctions
        Write-Host "卸载完成。"
        exit 0
    }

    if ($Install -or $DryRun) {
        Write-Host "== 兰亭生态插件安装（作用域隔离拓扑）=="
        if (-not (Invoke-InstallPlan)) { exit 0 }
        # 0. @deepseek-ai 解析桥（preset 插件 import 依赖的解析基准）
        if (-not (Test-AiBridge)) {
            $dshAiTarget = Get-DshAiTarget
            if (-not $dshAiTarget) { throw "找不到 dsh 运行时的 @deepseek-ai 目录（Get-Command dsh 探测失败），请确认 dsh 已安装。" }
            New-Item -ItemType Directory -Path (Split-Path $dshAiLink) -Force | Out-Null
            New-Item -ItemType Junction -Path $dshAiLink -Target $dshAiTarget | Out-Null
            Write-Step "AiBridge: $dshAiLink -> $dshAiTarget"
        }
        # 1. guard Junction（profile 层）
        if (-not (Test-GuardJunction)) {
            New-Item -ItemType Directory -Path $presalesScopeDir -Force | Out-Null
            $gLink = Join-Path $guardPlugin.ScopeDir $guardPlugin.Link
            if (Test-Path $gLink) { Remove-Item $gLink -Force -Recurse }
            New-Item -ItemType Junction -Path $gLink -Target $guardPlugin.Src | Out-Null
            Write-Step "guard Junction: $($guardPlugin.Link) -> $($guardPlugin.Src)"
        }
        # 2. profile patch：guard insert（原子写 + 备份）
        if (-not (Test-ProfilePatchLines)) {
            $content = Get-Content $patchPath -Raw -Encoding UTF8
            if (-not (Test-Path $patchBak)) { Copy-Item $patchPath $patchBak -Force }
            $entry = (Get-ProfilePatchLines) -join "`r`n"
            $content = $content.TrimEnd() + "`r`n" + $entry + "`r`n"
            Write-AtomicText $patchPath $content
            Write-Step "cordis.patch.yml 已追加 guard insert（备份: $patchBak）"
        }
        # 3. preset：不存在则从模板落盘，存在则追加 folio 两插件行（均备份）
        if (-not (Test-PresetLines)) {
            if (-not (Test-Path $presetFile)) {
                if (-not (Test-Path $presetSource)) { throw "发布仓库缺少 preset 模板: $presetSource" }
                $template = Get-Content $presetSource -Raw -Encoding UTF8
                $template = $template.Replace("__FOLIO_HOME__", (ConvertTo-Fwd $projRoot))
                New-Item -ItemType Directory -Path (Split-Path $presetFile) -Force | Out-Null
                Write-AtomicText $presetFile $template
                Write-Step "pre-sales preset 已从模板创建（含 folio 两插件行）"
            } else {
                $content = Get-Content $presetFile -Raw -Encoding UTF8
                if (-not (Test-Path $presetBak)) { Copy-Item $presetFile $presetBak -Force }
                $entry = (Get-PresetLines) -join "`r`n"
                $content = $content.TrimEnd() + "`r`n" + $entry + "`r`n"
                Write-AtomicText $presetFile $content
                Write-Step "pre-sales preset 已追加 folio 两插件行（备份: $presetBak）"
            }
        }
        # 4. 清理旧拓扑残留 Junction
        Remove-LegacyJunctions
        Write-Host "安装完成。**重启 dsh web 后生效**（host 插件无 HMR）。"
        exit 0
    }

    Write-Host "无操作。用法见脚本头部注释（-Install/-Verify/-Uninstall/-DryRun）。"
    exit 0
}
finally {
    if (Test-Path $lockPath) { Remove-Item $lockPath -Force }
}
