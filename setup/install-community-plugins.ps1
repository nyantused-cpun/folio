# install-community-plugins：兰亭 P0 社区插件一键接入
#
# 目标插件（以社区成熟生态为主）：
#   1. DSH-better-sidebar  -> 右侧预览区 / 迷你 IDE 工作台
#   2. dsh-github-connector -> GitHub 集成
#   3. context-vista        -> Token 可视化
#   4. dsh-agent-teams      -> 团队可视化
#
# 原理：
#   - 从 awesome-dsh-plugins README 自动解析各插件的 GitHub 仓库
#   - git clone 到 ~/.dsh/community-plugins/<key>
#   - 读取 package.json 得到真实包名
#   - 在 ~/.dsh/profiles/web/node_modules 下建 Junction
#   - 在 cordis.patch.yml 追加 insert 行
#   - 重启 dsh web 后生效
#
# 用法：
#   pwsh .dsh\setup\install-community-plugins.ps1 -Install
#   pwsh .dsh\setup\install-community-plugins.ps1 -Verify
#   pwsh .dsh\setup\install-community-plugins.ps1 -DryRun
#   pwsh .dsh\setup\install-community-plugins.ps1 -Uninstall
#
# 前置：已安装 git，且本机可访问 github / raw.githubusercontent.com。
#
# ⚠ 2026-08-15 决策：社区插件暂缓启用（保持「装而未挂」）。
#   原因：插件 peer 依赖 @deepseek-ai/*（cordis/dsh-*）在 profile node_modules
#   内缺失或形成双副本 → dsh-scope Symbol 分裂 → resume unscoped / web 启动失败。
#   官方 plugin 通道稳定后再启用。未确认依赖已解决前，勿跑 -Install。

param(
    [switch]$Install,
    [switch]$Verify,
    [switch]$DryRun,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$dshHome = Join-Path $env:USERPROFILE ".dsh"
$profileDir = Join-Path $dshHome "profiles\web"
$nodeModules = Join-Path $profileDir "node_modules"
$patchPath = Join-Path $profileDir "cordis.patch.yml"
$patchBak = Join-Path $profileDir "cordis.patch.yml.bak-community"
$pluginsRoot = Join-Path $dshHome "community-plugins"
$lockPath = Join-Path $dshHome ".community-plugins-install.lock"
$awesomeUrl = "https://raw.githubusercontent.com/AdamPlatin123/awesome-dsh-plugins/main/README.md"

$targets = @(
    @{ Key = "better-sidebar";    Package = "dsh-better-sidebar";              Patterns = @("DSH-better-sidebar", "better-sidebar", "dsh-better-sidebar") },
    @{ Key = "github-connector";  Package = "@perrylink/dsh-github";           Patterns = @("dsh-github-connector", "github-connector", "github") },
    @{ Key = "context-vista";     Package = "context-vista";                   Patterns = @("context-vista", "dsh-context-vista") },
    @{ Key = "agent-teams";       Package = "@nanmicoder/dsh-agent-teams";     Patterns = @("dsh-agent-teams", "agent-teams") }
)

function Write-Step([string]$msg) { Write-Host "  $msg" }

function Get-DshVersion {
    $v = & dsh --version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $v) { return "(无法获取 dsh 版本)" }
    return ($v | Select-Object -First 1)
}

function Get-AwesomeReadme {
    Write-Step "拉取 awesome-dsh-plugins README ..."
    $resp = Invoke-WebRequest -Uri $awesomeUrl -UseBasicParsing -TimeoutSec 30
    return $resp.Content
}

function Find-RepoUrl([string]$content, [string[]]$patterns) {
    foreach ($pat in $patterns) {
        $regex = "(?i)\[[^\]]*" + [regex]::Escape($pat) + "[^\]]*\]\(([^)]+)\)"
        $m = [regex]::Match($content, $regex)
        if ($m.Success) {
            $url = $m.Groups[1].Value.Trim()
            if ($url -match "github\.com") { return $url }
        }
    }
    return $null
}

function Get-GitUrl([string]$url) {
    if ($url -match "github\.com/([^/]+)/([^/]+)") {
        return "https://github.com/$($Matches[1])/$($Matches[2]).git"
    }
    return $url
}

function Test-Junction([string]$path) {
    if (-not (Test-Path $path)) { return $false }
    $item = Get-Item $path -Force
    return $item.LinkType -eq "Junction"
}

function Get-PatchText([string]$id, [string]$name) {
    return @(
        "# ── 兰亭社区插件（install-community-plugins.ps1 维护）──────────────────",
        "- insert:",
        "    - id: $id",
        "      name: `"$name`"",
        "      config: {}"
    ) -join "`r`n"
}

function Add-PatchEntry([string]$id, [string]$name) {
    if (-not (Test-Path $patchPath)) { throw "找不到 profile patch: $patchPath" }
    $content = Get-Content $patchPath -Raw -Encoding UTF8
    if ($content.Contains("name: `"$name`"")) {
        Write-Step "patch 已包含 $name，跳过"
        return
    }
    if (-not (Test-Path $patchBak)) { Copy-Item $patchPath $patchBak -Force }
    $entry = (Get-PatchText $id $name) + "`r`n"
    $content = $content.TrimEnd() + "`r`n" + $entry
    Set-Content -Path $patchPath -Value $content -Encoding UTF8 -NoNewline
    Write-Step "patch 已追加 $name"
}

function Install-One($target) {
    $key = $target.Key
    $pkg = $target.Package
    $repoDir = Join-Path $pluginsRoot $key
    Write-Host ""
    Write-Host "== $key =="

    # 优先走官方/社区发布渠道：dsh plugin add 会从 npm 拉已构建好的包，
    # 避免 git clone 源码后缺少 lib/ 或依赖的问题。
    if ($pkg) {
        Write-Step "尝试 dsh plugin --profile web add $pkg"
        if ($DryRun) {
            Write-Step "[DryRun] 将执行 dsh plugin --profile web add $pkg"
            return $true
        }
        & dsh plugin --profile web add $pkg
        if ($LASTEXITCODE -eq 0) {
            Write-Step "dsh plugin add 成功: $pkg"
            return $true
        }
        Write-Host "  [WARN] dsh plugin add 失败，回退 git clone 方式。" -ForegroundColor Yellow
    }

    # 回退：从 awesome 列表解析仓库并 git clone
    $content = Get-AwesomeReadme
    $url = Find-RepoUrl $content $target.Patterns
    if (-not $url) {
        Write-Host "  [WARN] awesome 列表未匹配到 $key，请手动到 awesome-dsh-plugins 确认仓库地址。" -ForegroundColor Yellow
        return $false
    }
    $gitUrl = Get-GitUrl $url
    Write-Step "仓库: $gitUrl"

    if (-not (Test-Path $repoDir)) {
        Write-Step "git clone --depth 1 $gitUrl $repoDir"
        if (-not $DryRun) {
            git clone --depth 1 $gitUrl $repoDir
            if ($LASTEXITCODE -ne 0) { throw "git clone 失败: $key" }
        }
    } else {
        Write-Step "目录已存在，尝试 git pull --ff-only"
        if (-not $DryRun) {
            Push-Location $repoDir
            git pull --ff-only
            Pop-Location
        }
    }

    if ($DryRun) {
        Write-Step "[DryRun] 不落盘，跳过 junction/patch"
        return $true
    }

    $pkgPath = Join-Path $repoDir "package.json"
    if (-not (Test-Path $pkgPath)) { throw "$key 缺少 package.json，无法自动接入" }
    $pkgObj = Get-Content $pkgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pkgName = $pkgObj.name
    if (-not $pkgName) { throw "$key package.json 缺少 name" }

    # 源码方式需要安装依赖并构建出 lib/
    Write-Step "安装依赖并构建（npm install && npm run build）"
    Push-Location $repoDir
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "$key npm install 失败" }
    if ($pkgObj.scripts.build) {
        npm run build
        if ($LASTEXITCODE -ne 0) { Pop-Location; throw "$key npm run build 失败" }
    }
    Pop-Location

    if ($pkgName.StartsWith("@")) {
        $parts = $pkgName.Split("/")
        $linkDir = Join-Path $nodeModules (Join-Path $parts[0] $parts[1])
    } else {
        $linkDir = Join-Path $nodeModules $pkgName
    }

    New-Item -ItemType Directory -Path (Split-Path $linkDir) -Force | Out-Null
    if (Test-Path $linkDir) {
        if (Test-Junction $linkDir) { Remove-Item $linkDir -Force }
        else { Remove-Item $linkDir -Force -Recurse }
    }
    New-Item -ItemType Junction -Path $linkDir -Target $repoDir | Out-Null
    Write-Step "Junction: $linkDir -> $repoDir"

    Add-PatchEntry $key $pkgName
    return $true
}

function Test-Installed {
    $ok = $true
    foreach ($t in $targets) {
        $pkgName = $t.Package
        if (-not $pkgName) { Write-Host "  [SKIP] $($t.Key) 无已知包名"; continue }
        if ($pkgName.StartsWith("@")) {
            $parts = $pkgName.Split("/")
            $pkgDir = Join-Path $nodeModules (Join-Path $parts[0] $parts[1])
        } else {
            $pkgDir = Join-Path $nodeModules $pkgName
        }
        $pkgExists = Test-Path (Join-Path $pkgDir "package.json")
        $patchOk = (Test-Path $patchPath) -and ((Get-Content $patchPath -Raw -Encoding UTF8).Contains("name: `"$pkgName`""))
        Write-Host ("  [{0}] {1}: package={2} patch={3}" -f $(if ($pkgExists -and $patchOk) { "OK" } else { "FAIL" }), $t.Key, $pkgExists, $patchOk)
        if (-not ($pkgExists -and $patchOk)) { $ok = $false }
    }
    return $ok
}

# ── 双副本护栏（2026-08-15 resume unscoped 事故）──────────────────────
# dsh plugin add / pnpm 安装社区插件时会把 @deepseek-ai 全家桶（含
# dsh-scope）拖进 profile 的 node_modules，与 dsh 主 bin 那套形成双实例。
# dsh-scope 用 Symbol("dsh.scope") 作 scope 键，双实例 Symbol 不互通 →
# 所有会话冷恢复报 "agent-presets: refusing to compose an unscoped context"。
# 官方核心组件必须由主 bin 统一提供，装完立即挪走副本。
function Remove-DuplicateDeepseekCopies([switch]$DryRunOnly) {
    $hits = @(
        (Join-Path $nodeModules "@deepseek-ai"),
        (Join-Path (Join-Path $dshHome "profiles\node_modules") "@deepseek-ai")
    )
    foreach ($nm in $hits) {
        if (-not (Test-Path $nm)) { continue }
        $bak = Join-Path (Split-Path $nm) "deepseek-ai.bak-dup"
        if ($DryRunOnly) {
            Write-Host "  [护栏][DryRun] 检测到官方包副本，将挪走: $nm" -ForegroundColor Yellow
            continue
        }
        if (Test-Path $bak) { Remove-Item $bak -Force -Recurse }
        Move-Item $nm $bak -Force
        Write-Host "  [护栏] 已挪走 dsh 官方包副本 -> $bak（防 dsh-scope Symbol 分裂）" -ForegroundColor Yellow
    }
}

function Test-NoDeepseekCopies {
    $clean = $true
    foreach ($nm in @(
        (Join-Path $nodeModules "@deepseek-ai"),
        (Join-Path (Join-Path $dshHome "profiles\node_modules") "@deepseek-ai")
    )) {
        if (Test-Path $nm) {
            Write-Host "  [FAIL] 存在官方包副本（会导致 resume unscoped）: $nm" -ForegroundColor Red
            $clean = $false
        }
    }
    return $clean
}

try {
    if (Test-Path $lockPath) {
        $lockAge = (Get-Date) - (Get-Item $lockPath).LastWriteTime
        if ($lockAge.TotalMinutes -lt 10) { Write-Host "另一实例运行中，跳过。"; exit 0 }
        Remove-Item $lockPath -Force
    }
    Set-Content -Path $lockPath -Value "locked" -Encoding UTF8

    if ($Verify) {
        Write-Host "== 社区插件验证 =="
        Write-Host "  DSH 版本: $(Get-DshVersion)"
        $ok = Test-Installed
        $clean = Test-NoDeepseekCopies
        $ok = $ok -and $clean
        Write-Host ("验证结果: {0}" -f $(if ($ok) { "PASS（重启 dsh web 后生效）" } else { "FAIL" }))
        exit $(if ($ok) { 0 } else { 1 })
    }

    if ($Uninstall) {
        Write-Host "== 社区插件卸载 =="
        foreach ($t in $targets) {
            $pkgName = $t.Package
            if ($pkgName) {
                if ($pkgName.StartsWith("@")) {
                    $parts = $pkgName.Split("/")
                    $linkDir = Join-Path $nodeModules (Join-Path $parts[0] $parts[1])
                } else {
                    $linkDir = Join-Path $nodeModules $pkgName
                }
                if (Test-Path $linkDir) { Remove-Item $linkDir -Force -Recurse; Write-Step "删 node_modules: $pkgName" }
            }
            $repoDir = Join-Path $pluginsRoot $t.Key
            if (Test-Path $repoDir) { Remove-Item $repoDir -Force -Recurse; Write-Step "删 clone: $($t.Key)" }
        }
        # 只摘除社区插件段，绝不整体还原备份——patch 里可能有 guard 等
        # 其他插件的最新结构，旧备份覆盖会丢掉它们（2026-08-15 踩坑）。
        $communityMarker = "# ── 兰亭社区插件（install-community-plugins.ps1 维护）"
        $content = Get-Content $patchPath -Raw -Encoding UTF8
        $idx = $content.IndexOf($communityMarker)
        if ($idx -ge 0) {
            $newContent = $content.Substring(0, $idx).TrimEnd() + "`r`n"
            Set-Content -Path $patchPath -Value $newContent -Encoding UTF8 -NoNewline
            Write-Step "已从 patch 摘除社区插件段（保留 guard 等既有结构）"
        } else {
            Write-Step "patch 中未发现社区插件段，无需处理"
        }
        Write-Host "卸载完成。"
        exit 0
    }

    if ($Install -or $DryRun) {
        Write-Host "== 兰亭 P0 社区插件安装 =="
        Write-Host "  DSH 版本: $(Get-DshVersion)"
        Write-Host "目标: better-sidebar / github-connector / context-vista / agent-teams"
        if ($DryRun) { Write-Host "[DryRun] 只解析不落盘" }
        $allOk = $true
        foreach ($t in $targets) {
            $r = Install-One $t
            if (-not $r) { $allOk = $false }
        }
        Write-Host ""
        Remove-DuplicateDeepseekCopies -DryRunOnly:$DryRun
        if ($allOk) {
            Write-Host "安装完成。**重启 dsh web 后生效**。" -ForegroundColor Green
        } else {
            Write-Host "部分插件未自动接入，请按上方 WARN 手动确认。" -ForegroundColor Yellow
        }
        exit $(if ($allOk) { 0 } else { 2 })
    }

    Write-Host "无操作。用法见脚本头部注释（-Install/-Verify/-DryRun/-Uninstall）。"
    exit 0
} finally {
    if (Test-Path $lockPath) { Remove-Item $lockPath -Force }
}
