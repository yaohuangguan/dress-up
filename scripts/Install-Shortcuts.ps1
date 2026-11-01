$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonWindow = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindow)) { throw 'Install the project with Setup.cmd first.' }
$entryScript = Join-Path $projectRoot 'desktop.py'
$iconFile = Join-Path $projectRoot 'web\app.ico'
$wscriptShell = New-Object -ComObject WScript.Shell
foreach ($shortcutFolder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $shortcutFile = Join-Path $shortcutFolder '衣见.lnk'
    if (Test-Path -LiteralPath $shortcutFile) {
        $existing = $wscriptShell.CreateShortcut($shortcutFile)
        if ($existing.TargetPath -ne $pythonWindow -or $existing.Arguments -ne ('"' + $entryScript + '"')) { throw 'An unrelated shortcut named 衣见 already exists; left unchanged.' }
    }
    $shortcut = $wscriptShell.CreateShortcut($shortcutFile)
    $shortcut.TargetPath = $pythonWindow
    $shortcut.Arguments = '"' + $entryScript + '"'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = $iconFile
    $shortcut.Description = '衣见 · 自动启动本地 AI 搭配工作室'
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Output ('Installed shortcut: ' + $shortcutFile)
}
