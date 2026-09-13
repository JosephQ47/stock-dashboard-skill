# 在 Claude Code 与 Codex 两端创建指向本 skill 的目录联接。可重复执行。
$ErrorActionPreference = "Stop"
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$targets = @(
    (Join-Path $env:USERPROFILE ".claude\skills\stock-dashboard"),
    (Join-Path $env:USERPROFILE ".codex\skills\stock-dashboard")
)

foreach ($t in $targets) {
    $parent = Split-Path -Parent $t
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path $t) {
        $item = Get-Item $t -Force
        if ($item.LinkType -eq "Junction") {
            Remove-Item $t -Force -Recurse
            Write-Host "移除旧联接 $t"
        } else {
            Write-Error "$t 是真实目录而非联接，为避免误删已中止。请手动处理后重试。"
        }
    }
    New-Item -ItemType Junction -Path $t -Target $src | Out-Null
    Write-Host "已联接 $t -> $src"
}

Write-Host ""
Write-Host "安装完成。验证："
foreach ($t in $targets) {
    $ok = Test-Path (Join-Path $t "SKILL.md")
    Write-Host ("  {0}  SKILL.md 可读: {1}" -f $t, $ok)
}

