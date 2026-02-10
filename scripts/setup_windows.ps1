# =============================================================================
#  Phase 1: Windows-side setup for qlib_rd_agent
#  Target: Windows 10 PC with NVIDIA GTX 3060
#
#  This script:
#    1. Enables WSL2 and Virtual Machine Platform
#    2. Installs Ubuntu 22.04 on WSL2
#    3. Copies the setup_wsl.sh script into WSL for Phase 2
#
#  Usage:
#    1. Open PowerShell as ADMINISTRATOR (right-click → Run as administrator)
#    2. If needed, allow script execution:
#         Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#    3. Run:
#         .\scripts\setup_windows.ps1
#
#  After this script completes and the PC reboots:
#    1. Open Ubuntu from Start menu (first launch sets up username/password)
#    2. Run Phase 2 inside WSL:
#         cd ~/qlib_rd_agent && chmod +x scripts/setup_wsl.sh && ./scripts/setup_wsl.sh
# =============================================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  qlib_rd_agent — Windows Setup (Phase 1)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 0. Check: running as Administrator
# ---------------------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script must be run as Administrator." -ForegroundColor Red
    Write-Host "  Right-click PowerShell → 'Run as administrator', then retry." -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Running as Administrator" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 0.1 Check: BIOS virtualisation enabled
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== [0/5] Checking virtualisation support ===" -ForegroundColor Yellow

$vmEnabled = (Get-CimInstance -ClassName Win32_Processor).VirtualizationFirmwareEnabled
if ($vmEnabled -eq $true) {
    Write-Host "[OK] Hardware virtualisation (VT-x / AMD-V) is enabled in BIOS" -ForegroundColor Green
} else {
    Write-Host "[WARNING] Hardware virtualisation may not be enabled in BIOS." -ForegroundColor Red
    Write-Host "  WSL2 requires VT-x (Intel) or AMD-V (AMD) to be enabled." -ForegroundColor Yellow
    Write-Host "  If WSL2 fails to start later, reboot into BIOS and enable it." -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y" -and $continue -ne "Y") { exit 0 }
}

# ---------------------------------------------------------------------------
# 1. Enable WSL feature
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== [1/5] Enabling Windows Subsystem for Linux ===" -ForegroundColor Yellow

$wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
if ($wslFeature.State -eq "Enabled") {
    Write-Host "[OK] WSL feature already enabled" -ForegroundColor Green
} else {
    Write-Host "Enabling WSL feature (may take a minute)..."
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart | Out-Null
    Write-Host "[OK] WSL feature enabled" -ForegroundColor Green
    $needsReboot = $true
}

# ---------------------------------------------------------------------------
# 2. Enable Virtual Machine Platform
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== [2/5] Enabling Virtual Machine Platform ===" -ForegroundColor Yellow

$vmpFeature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
if ($vmpFeature.State -eq "Enabled") {
    Write-Host "[OK] Virtual Machine Platform already enabled" -ForegroundColor Green
} else {
    Write-Host "Enabling Virtual Machine Platform..."
    Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart | Out-Null
    Write-Host "[OK] Virtual Machine Platform enabled" -ForegroundColor Green
    $needsReboot = $true
}

# ---------------------------------------------------------------------------
# 3. Check if reboot needed before continuing
# ---------------------------------------------------------------------------
if ($needsReboot) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Magenta
    Write-Host "  REBOOT REQUIRED" -ForegroundColor Magenta
    Write-Host "============================================" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "WSL2 features have been enabled but require a reboot." -ForegroundColor Yellow
    Write-Host "After rebooting, run this script AGAIN to continue from step 3." -ForegroundColor Yellow
    Write-Host ""
    $rebootNow = Read-Host "Reboot now? (y/N)"
    if ($rebootNow -eq "y" -or $rebootNow -eq "Y") {
        Restart-Computer
    }
    exit 0
}

# ---------------------------------------------------------------------------
# 4. Set WSL2 as default & install Ubuntu 22.04
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== [3/5] Setting WSL 2 as default version ===" -ForegroundColor Yellow
wsl --set-default-version 2
Write-Host "[OK] WSL 2 set as default" -ForegroundColor Green

Write-Host ""
Write-Host "=== [4/5] Installing Ubuntu 22.04 ===" -ForegroundColor Yellow

# Check if Ubuntu is already installed
$wslList = wsl -l -q 2>$null
if ($wslList -match "Ubuntu") {
    Write-Host "[OK] Ubuntu already installed in WSL" -ForegroundColor Green
} else {
    Write-Host "Installing Ubuntu 22.04 (this may take a few minutes)..."
    Write-Host "  You will be asked to create a UNIX username and password." -ForegroundColor Cyan
    Write-Host ""
    wsl --install -d Ubuntu-22.04
    Write-Host ""
    Write-Host "[OK] Ubuntu 22.04 installed" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 5. Copy project into WSL
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== [5/5] Copying qlib_rd_agent project into WSL ===" -ForegroundColor Yellow

# Determine project source (this script lives in scripts/, project is parent dir)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir

# WSL home directory path from Windows side
# wsl converts Windows path automatically when using wsl.exe commands
Write-Host "Source: $projectDir"
Write-Host "Destination: ~/qlib_rd_agent (inside WSL)"

# Create target dir and copy via WSL
wsl -d Ubuntu-22.04 -- bash -c "mkdir -p ~/qlib_rd_agent"
# Use robocopy-like approach: copy from Windows path to WSL via /mnt/
$winDrive = $projectDir.Substring(0, 1).ToLower()
$winPath = $projectDir.Substring(2).Replace("\", "/")
$wslSourcePath = "/mnt/$winDrive$winPath"

wsl -d Ubuntu-22.04 -- bash -c "cp -r $wslSourcePath/* ~/qlib_rd_agent/ && cp -r $wslSourcePath/.* ~/qlib_rd_agent/ 2>/dev/null; echo 'Copy done'"
wsl -d Ubuntu-22.04 -- bash -c "chmod +x ~/qlib_rd_agent/scripts/*.sh"

Write-Host "[OK] Project copied to ~/qlib_rd_agent in WSL" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Phase 1 Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next: Run Phase 2 inside WSL to install all tools:" -ForegroundColor Cyan
Write-Host ""
Write-Host '  1. Open "Ubuntu 22.04" from the Start menu' -ForegroundColor White
Write-Host "     (or run: wsl -d Ubuntu-22.04)" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Run the WSL setup script:" -ForegroundColor White
Write-Host '     cd ~/qlib_rd_agent && ./scripts/setup_wsl.sh' -ForegroundColor White
Write-Host ""
Write-Host "  Phase 2 will install:" -ForegroundColor Gray
Write-Host "    - System packages (build-essential, git, curl, etc.)" -ForegroundColor Gray
Write-Host "    - Miniforge (conda-forge, NOT Anaconda)" -ForegroundColor Gray
Write-Host "    - CUDA Toolkit 12.1 (for PyTorch GPU)" -ForegroundColor Gray
Write-Host "    - uv (Python package manager)" -ForegroundColor Gray
Write-Host "    - rdagent4qlib conda env (Python 3.10, RD-Agent, Qlib, PyTorch)" -ForegroundColor Gray
Write-Host "    - qlib_rd_agent project venv" -ForegroundColor Gray
Write-Host ""
