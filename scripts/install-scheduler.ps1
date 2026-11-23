param(
    [string]$Python = "python",
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TaskName = "WooriYouTubeAgent-Daily",
    [string]$RunAt = "05:00"
)
$action = New-ScheduledTaskAction -Execute $Python -Argument "-m woori_youtube.runner" -WorkingDirectory $ProjectPath
$trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Build and validate the daily Woori YouTube news video" -Force
Write-Host "Installed scheduled task '$TaskName'. It does not publish publicly unless the explicit public-verification gate is configured."
