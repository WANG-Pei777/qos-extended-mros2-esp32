# Run this from an elevated Windows PowerShell.
# It allows DDS/RTPS UDP traffic used by the WSL2 ROS2 <-> ESP32 mROS2 validation workflow.

$ErrorActionPreference = "Stop"

$vmCreatorId = "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}"
$ruleName = "mros2-dds-rtps-wsl-udp-7400-7420"
$displayName = "mROS2 DDS RTPS WSL UDP 7400-7420"

Write-Host "[mros2] Configuring Hyper-V firewall for WSL2 mirrored networking..."

$existing = Get-NetFirewallHyperVRule -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq $ruleName }
if ($existing) {
  $existing | Remove-NetFirewallHyperVRule
}

New-NetFirewallHyperVRule `
  -Name $ruleName `
  -DisplayName $displayName `
  -Direction Inbound `
  -VMCreatorId $vmCreatorId `
  -Protocol UDP `
  -LocalPorts 7400-7420 `
  -Action Allow `
  -Enabled True | Out-Null

$classicRuleName = "mROS2 DDS RTPS UDP 7400-7420"
$classicExisting = Get-NetFirewallRule -DisplayName $classicRuleName -ErrorAction SilentlyContinue
if ($classicExisting) {
  $classicExisting | Remove-NetFirewallRule
}

New-NetFirewallRule `
  -DisplayName $classicRuleName `
  -Direction Inbound `
  -Protocol UDP `
  -LocalPort 7400-7420 `
  -Action Allow `
  -Profile Any | Out-Null

Write-Host "[mros2] Done. Rules installed:"
Get-NetFirewallHyperVRule |
  Where-Object { $_.Name -eq $ruleName } |
  Format-Table -AutoSize DisplayName,Direction,Protocol,LocalPorts,Action,Enabled
Get-NetFirewallRule -DisplayName $classicRuleName |
  Format-Table -AutoSize DisplayName,Direction,Action,Enabled
