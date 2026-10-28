# Removes the daily task and desktop shortcuts. Your files, preferences and documents are kept.
$TaskName = "Job Agent - daily search"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$Desktop = [Environment]::GetFolderPath("Desktop")
foreach ($name in @("Review jobs", "Search jobs now", "Job agent folder")) {
    Remove-Item (Join-Path $Desktop "$name.lnk") -ErrorAction SilentlyContinue
}
Write-Host "Removed the daily task and desktop shortcuts. Delete the job-agent folder too if you want everything gone."
