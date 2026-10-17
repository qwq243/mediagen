[CmdletBinding()]
param()

# Keep this file encoded as UTF-8 with BOM for Windows PowerShell 5.1.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$apiBase = "https://api.toapi.xyz/v1"

try {
    $Host.UI.RawUI.WindowTitle = "配置 NewAPI 生图密钥"
} catch {
    # Some terminal hosts do not expose a writable title.
}

Write-Host ""
Write-Host "NewAPI 生图配置" -ForegroundColor Cyan
Write-Host "接口地址：$apiBase"
Write-Host "密钥将在本机隐藏输入，不会显示在窗口或写入项目文件。"
Write-Host ""

$plainKey = $null
for ($attempt = 1; $attempt -le 3; $attempt += 1) {
    $secureKey = Read-Host "请输入新的 NewAPI API Key" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $candidate = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        if ($candidate -match '^sk-[A-Za-z0-9_-]{16,}$' -and $candidate -notmatch '\s') {
            $plainKey = $candidate
            break
        }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        Remove-Variable secureKey -ErrorAction SilentlyContinue
    }
    Write-Warning "密钥格式不正确，请确认以 sk- 开头且没有空格。"
}

if (-not $plainKey) {
    Write-Error "连续三次输入无效，未修改任何配置。"
    Read-Host "按回车关闭窗口"
    exit 1
}

try {
    [Environment]::SetEnvironmentVariable("NEWAPI_BASE_URL", $apiBase, "User")
    [Environment]::SetEnvironmentVariable("NEWAPI_API_KEY", $plainKey, "User")
    $env:NEWAPI_BASE_URL = $apiBase
    $env:NEWAPI_API_KEY = $plainKey
} finally {
    $plainKey = $null
    $candidate = $null
    Remove-Variable plainKey -ErrorAction SilentlyContinue
    Remove-Variable candidate -ErrorAction SilentlyContinue
}

$storedBase = [Environment]::GetEnvironmentVariable("NEWAPI_BASE_URL", "User")
$storedKey = [Environment]::GetEnvironmentVariable("NEWAPI_API_KEY", "User")
$keyLooksValid = [bool]($storedKey -match '^sk-[A-Za-z0-9_-]{16,}$' -and $storedKey -notmatch '\s')

if ($storedBase -ne $apiBase -or -not $keyLooksValid) {
    Write-Error "写入后的本机校验未通过，请重新运行脚本。"
    Read-Host "按回车关闭窗口"
    exit 1
}

$keyLength = $storedKey.Length
$storedKey = $null
Remove-Variable storedKey -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "配置已写入当前 Windows 用户环境变量。" -ForegroundColor Green
Write-Host "接口地址：$storedBase"
Write-Host "密钥状态：已保存，格式有效，长度 $keyLength（内容不显示）"
Write-Host "回到 Codex 后回复：已更新"
Write-Host ""
Read-Host "按回车关闭窗口"
