# install-all：兰亭自研插件 + P0 社区插件一键安装
#
# 用法：
#   pwsh .\setup\install-all.ps1                        # 只装自研（guard + folio-tools + folio-events）
#   pwsh .\setup\install-all.ps1 -IncludeCommunity      # 额外尝试装社区插件（当前默认跳过）
#
# 社区插件当前「装而未挂」（2026-08-15 决策）：peer 依赖在 profile node_modules
# 缺失或双副本 → dsh-scope Symbol 分裂 → resume unscoped / web 启动失败。
# 官方 plugin 通道稳定前勿默认启用；-IncludeCommunity 时也由
# install-community-plugins.ps1 内部的暂缓保护决定是否实际安装。

param(
    [switch]$IncludeCommunity
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 1/1 兰亭自研插件安装" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
& (Join-Path $scriptRoot "install-folio-plugins.ps1") -Install
if ($LASTEXITCODE -ne 0) { Write-Host "自研插件安装失败，停止。"; exit $LASTEXITCODE }

if ($IncludeCommunity) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " 2/2 P0 社区插件安装（暂缓保护生效时自动跳过）" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    & (Join-Path $scriptRoot "install-community-plugins.ps1") -Install
    if ($LASTEXITCODE -ne 0) { Write-Host "社区插件安装未完全成功，请查看上方 WARN。"; exit $LASTEXITCODE }
} else {
    Write-Host ""
    Write-Host "社区插件未安装（默认跳过：peer 依赖暂缓）。需要时用 -IncludeCommunity。"
}

Write-Host ""
Write-Host "全部执行完毕。请重启 dsh web 后验证。" -ForegroundColor Green
