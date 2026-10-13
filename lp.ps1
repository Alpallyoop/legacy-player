<#
.SYNOPSIS
lp - one small command for Legacy Player. Run  .\lp.cmd help  for the list (in PowerShell a bare .\lp runs this .ps1, which the default execution policy blocks).
#>
param(
    [Parameter(Position = 0)][string]$Command = 'help',
    [Parameter(Position = 1)][string]$Tag = '',
    [string]$Repo = 'Alpallyoop/legacy-player',
    [string]$Token = "",
    [string]$Dest = '',
    [switch]$NoLaunch
)
$usage = @'
 lp - one small command for Legacy Player (Windows PowerShell or PowerShell 7).

   git clone https://github.com/Alpallyoop/legacy-player
   cd legacy-player
   .\lp.cmd install             download the newest release, check its SHA-256 and install it into this folder's
                                app\ subfolder (no administrator; nothing goes to AppData). -Dest <folder> picks another place
   .\lp.cmd install v0.7.48     the same, for one exact version
   .\lp.cmd update              install the newest release over the current one (your saves and settings stay)
   .\lp.cmd run                 start the installed app
   .\lp.cmd version             what is installed, and what is the newest
   .\lp.cmd path                where it is installed (your files are in LegacyPlayerData there, unless you chose a folder)
   .\lp.cmd uninstall           remove the program and its Start menu shortcut (LegacyPlayerData stays; the in-app doctor removes that)
   .\lp.cmd remove-old          remove an older copy installed in %LOCALAPPDATA%\Programs\LegacyPlayer (move your files out
                                of it first: in the app, Settings > Where Legacy Player keeps its files > Change)
   .\lp.cmd source              run straight from this git checkout with Python 3.13+ (no download, for developers;
                                its files go to the checkout's data folder)
   .\lp.cmd test                run the test suite from this checkout (temporary files stay in .tmp\ here)
   .\lp.cmd help

 From cmd.exe plain  lp install  works. Without lp.cmd:  powershell -ExecutionPolicy Bypass -File .\lp.ps1 install

 Add  -Repo owner/name  to use a fork, or  -Token <github token>  for a private repository.
'@
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# The program lives in this project's own folder (app\, ignored by git), not in AppData: everything for this project stays
# in one place. -Dest picks another folder.
$dest = if ($Dest) { $Dest } else { Join-Path $PSScriptRoot 'app' }
$oldDest = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Programs\LegacyPlayer' } else { '' }
$exe = Join-Path $dest 'LegacyPlayer.exe'
$programs = [Environment]::GetFolderPath('Programs')
$lnk = if ($programs) { Join-Path $programs 'Legacy Player.lnk' } else { '' }

function Get-Latest {
    $h = @{ 'User-Agent' = 'LegacyPlayer-lp'; 'Accept' = 'application/vnd.github+json' }
    if ($Token) { $h['Authorization'] = "Bearer $Token" }
    try { (Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $h).tag_name } catch { $null }
}
function Get-Installed {
    $f = Join-Path $dest 'VERSION.txt'
    if (Test-Path $f) { (Get-Content $f -Raw).Trim() } elseif (Test-Path $exe) { 'unknown version' } else { $null }
}
function Invoke-Install {
    $script = Join-Path $PSScriptRoot 'install.ps1'
    if (-not (Test-Path $script)) { throw "install.ps1 is missing next to lp.ps1. Clone the repository again: git clone https://github.com/$Repo" }
    $args2 = @{ Repo = $Repo; Token = $Token; Dest = $dest }
    if ($Tag) { $args2['Tag'] = $Tag }
    if ($NoLaunch) { $args2['NoLaunch'] = $true }
    & $script @args2
}
function Stop-App {
    foreach ($p in @(Get-Process -Name LegacyPlayer -ErrorAction SilentlyContinue)) {
        try {
            $p.CloseMainWindow() | Out-Null; Start-Sleep 2
            if (-not $p.HasExited) { $p.Kill(); $p.WaitForExit(5000) | Out-Null }
        } catch { }
        if (-not $p.HasExited) { Write-Host "Could not close Legacy Player (process $($p.Id)); close it yourself and try again." -ForegroundColor Yellow }
    }
}

switch ($Command.ToLower()) {
    { $_ -in 'install', 'update', 'upgrade' } {
        Invoke-Install
    }
    'run' {
        if (-not (Test-Path $exe)) { throw "Legacy Player is not installed yet. Run:  .\lp.cmd install" }
        Start-Process $exe
    }
    'version' {
        $have = Get-Installed
        $latest = Get-Latest
        Write-Host ("Installed: " + $(if ($have) { $have } else { 'not installed' }))
        Write-Host ("Newest:    " + $(if ($latest) { $latest } else { 'could not reach GitHub' }))
        if ($have -and $latest -and $have -ne $latest -and $have -ne 'unknown version') { Write-Host "An update is available:  .\lp.cmd update" }
    }
    'path' { Write-Output $dest }
    'remove-old' {
        if (-not $oldDest -or -not (Test-Path -LiteralPath $oldDest)) { Write-Host 'There is no older copy in AppData.'; break }
        if ((Split-Path $oldDest -Leaf) -ne 'LegacyPlayer') { throw 'Refusing to remove an unexpected folder.' }
        $oldData = Join-Path $oldDest 'LegacyPlayerData'
        if ((Test-Path -LiteralPath $oldData) -and (Get-ChildItem -LiteralPath $oldData -Force -ErrorAction SilentlyContinue)) {
            Write-Host "Your files are still in $oldData." -ForegroundColor Yellow
            Write-Host "Move them first: open Legacy Player, Settings > Where Legacy Player keeps its files > Change, and pick a folder here (for example $(Join-Path $dest 'LegacyPlayerData'))."
            Write-Host "Then run  .\lp.cmd remove-old  again. Nothing was removed."
            break
        }
        Stop-App
        foreach ($name in @('LegacyPlayer.exe', '_internal', 'VERSION.txt', 'READ ME FIRST.txt', 'LICENSE', 'data-location.txt', 'LegacyPlayerData')) {
            $p = Join-Path $oldDest $name
            if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
        }
        if (-not (Get-ChildItem -LiteralPath $oldDest -Force -ErrorAction SilentlyContinue)) { Remove-Item -LiteralPath $oldDest -Force }
        if ($lnk -and (Test-Path -LiteralPath $exe)) {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($lnk); $shortcut.TargetPath = $exe; $shortcut.WorkingDirectory = $dest; $shortcut.Save()
            Write-Host "The Start menu shortcut now opens $exe."
        }
        Write-Host "Removed the older copy from $oldDest."
    }
    'uninstall' {
        if (-not (Test-Path $dest)) { Write-Host 'Legacy Player is not installed.'; break }
        if ((Split-Path $dest -Leaf) -ne 'LegacyPlayer') { throw 'Refusing to remove an unexpected folder.' }
        Stop-App
        # only the program itself: LegacyPlayerData (settings, emulators, saves, logs) and data-location.txt stay
        foreach ($name in @('LegacyPlayer.exe', '_internal', 'VERSION.txt', 'READ ME FIRST.txt', 'LICENSE')) {
            $p = Join-Path $dest $name
            if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
        }
        if (-not (Get-ChildItem -LiteralPath $dest -Force -ErrorAction SilentlyContinue)) { Remove-Item -LiteralPath $dest -Force }
        if ($lnk) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue }
        Write-Host "Removed the program. Your games, saves and settings were not touched."
        if (Test-Path -LiteralPath (Join-Path $dest 'LegacyPlayerData')) { Write-Host "They are still in $(Join-Path $dest 'LegacyPlayerData')." }
        Write-Host "To remove those as well, use the doctor in the app (Uninstall Legacy Player) before running this."
    }
    { $_ -in 'source', 'test' } {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { throw 'Python 3.13+ was not found. Install it from python.org (tick "Add to PATH") and try again.' }
        # Keep everything for this project in this folder: temporary files, Python's caches and the test run's scratch
        # folders go to .tmp\ and .cache\ here (both ignored by git), not to %TEMP% or AppData on the system drive.
        $tmp = Join-Path $PSScriptRoot '.tmp'; $cache = Join-Path $PSScriptRoot '.cache'
        New-Item -ItemType Directory -Force -Path $tmp, $cache | Out-Null
        $env:TEMP = $tmp; $env:TMP = $tmp
        $env:PYTHONPYCACHEPREFIX = Join-Path $cache 'pycache'
        $env:PIP_CACHE_DIR = Join-Path $cache 'pip'
        $env:PLAYWRIGHT_BROWSERS_PATH = if ($env:PLAYWRIGHT_BROWSERS_PATH) { $env:PLAYWRIGHT_BROWSERS_PATH } else { Join-Path $cache 'ms-playwright' }
        Push-Location $PSScriptRoot                  # the repository folder, wherever the command was typed
        try {
            if ($_ -eq 'test') { & python -W ignore -m unittest discover -s tests -q }
            else { & python -m launcher }
        } finally { Pop-Location }
    }
    default { Write-Host $usage }
}
