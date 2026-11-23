param([string]$TaskName = "WooriYouTubeAgent-Trends")
$ErrorActionPreference = "Stop"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Task $TaskName already exists; inspect it before changing it."
}
$script = Join-Path $PSScriptRoot "collect-trends.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory (Split-Path $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Collect public US Trends RSS every 30 minutes" | Out-Null
Write-Host "Installed $TaskName. This task collects trends only."
