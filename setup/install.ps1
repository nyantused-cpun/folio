# Folio one-shot installer (Windows first)
# Usage:  powershell -ExecutionPolicy Bypass -File .\setup\install.ps1
# Creates .venv, installs deps, generates .env, prints capability level.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root   # setup/ -> repo root
Set-Location $root

Write-Host ""
Write-Host "  Lan Ting (Folio) installer" -ForegroundColor Cyan
Write-Host "  ===========================" -ForegroundColor Cyan
Write-Host ""

# ---------- Step 1: Python >= 3.10 ----------
$py = $null
foreach ($candidate in @("py", "python", "python3")) {
    try {
        $v = & $candidate -c "import sys; print(sys.version_info[:2])" 2>$null
        if ($v -match "\((\d+),\s*(\d+)\)") {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if (($maj -gt 3) -or ($maj -eq 3 -and $min -ge 10)) {
                $py = $candidate
                Write-Host "  [OK] Python $maj.$min ($candidate)" -ForegroundColor Green
                break
            }
        }
    } catch { }
}
if (-not $py) {
    Write-Host "  [FAIL] Python >= 3.10 not found. Install from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# ---------- Step 2: venv + dependencies ----------
if (-not (Test-Path ".venv")) {
    Write-Host "  [..] Creating .venv ..."
    & $py -m venv .venv
}
$pip = ".venv\Scripts\python.exe"
Write-Host "  [..] Installing dependencies (requirements.txt) ..."
& $pip -m pip install --quiet --upgrade pip
& $pip -m pip install --quiet -r requirements.txt

# ---------- Step 3: dependency import check ----------
$mods = "flask","jieba","numpy","openpyxl","PIL","fitz","docx","pptx","yaml","requests","ruamel.yaml"
$missing = @()
foreach ($m in $mods) {
    & $pip -c "import $m" 2>$null
    if ($LASTEXITCODE -ne 0) { $missing += $m }
}
if ($missing.Count -eq 0) {
    Write-Host "  [OK] 11 core dependencies import fine" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Missing imports: $($missing -join ', ')" -ForegroundColor Yellow
}

# ---------- Step 4: PPT conversion backend ----------
# 2026-08-16 更新：转换后端为自研 python-pptx（Step 3 的 pptx import 即检查）；
# 不再依赖 node 工具链。--shots 截图目检需要本机 PowerPoint（COM），无则跳过。
$hasPptx = & $pip -c "import pptx" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] python-pptx found: PPT conversion backend available" -ForegroundColor Green
} else {
    Write-Host "  [WARN] python-pptx import failed. PPT conversion unavailable until deps are fixed." -ForegroundColor Yellow
    Write-Host "         Run: $pip -m pip install -r requirements.txt" -ForegroundColor Yellow
}

# ---------- Step 5: .env generation ----------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  [OK] .env generated from .env.example (all keys empty = L0, works)" -ForegroundColor Green
} else {
    Write-Host "  [OK] .env exists (kept as-is)" -ForegroundColor Green
}

# ---------- Step 6: capability level ----------
$envPath = Join-Path $root ".env"
Get-Content $envPath -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=\s*(\S*)') { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] }
}
$level = "L0 (zero-key: BM25 recall + render + quality gates; DSH host covers vision/search/review)"
$hasEmbed = $env:ZHIPU_API_KEY -or $env:SILICONFLOW_API_KEY
# 视觉槽位：内置 provider 默认 MiniMax；如替换为其他 OpenAI 兼容视觉端点，在此按对应 key 扩展检测
$hasVision = $env:MINIMAX_API_KEY
$hasSearch = $env:TAVILY_API_KEY -or $env:ASK_ECHO_SEARCH_INFINITY_API_KEY
if ($hasEmbed) {
    $level = "L1 (+semantic recall)"
    if ($hasVision -or $hasSearch) { $level = "L2 (+vision/search for standalone CLI)" }
}
Write-Host ""
Write-Host "  Capability level: $level" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "    1. Restart DSH (or your AI host)."
Write-Host "    2. Open a new session in this folder."
Write-Host "    3. Say: '帮我做一份 XX 方案' - the engine's skills load automatically."
Write-Host "    4. Run self-check anytime: .venv\Scripts\python.exe src\_cli.py key-doctor"
Write-Host ""
Write-Host "  Done." -ForegroundColor Green
