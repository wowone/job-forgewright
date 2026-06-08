# Cross-platform runner for latent-cli
# Auto-detects OS and architecture, then runs the appropriate binary

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BinDir = Join-Path $ScriptDir "bin"

# Detect OS
$OS = switch ($env:OS) {
    "Windows_NT" { "windows" }
    default {
        if ($IsMacOS) { "darwin" }
        elseif ($IsLinux) { "linux" }
        else { "unknown" }
    }
}

# If OS detection failed, try uname
if ($OS -eq "unknown" -and $IsLinux) {
    try {
        $uname = uname -s
        if ($uname -like "*Darwin*") { $OS = "darwin" }
        elseif ($uname -like "*Linux*") { $OS = "linux" }
    } catch {}
}

# Detect architecture
$Arch = switch ([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture) {
    ([System.Runtime.InteropServices.Architecture]::X64) { "amd64" }
    ([System.Runtime.InteropServices.Architecture]::Arm64) { "arm64" }
    default {
        # Fallback to environment variable
        switch ($env:PROCESSOR_ARCHITECTURE) {
            "AMD64" { "amd64" }
            "ARM64" { "arm64" }
            default { "unknown" }
        }
    }
}

# Alternative arch detection for older PowerShell
if ($Arch -eq "unknown") {
    try {
        $uname_m = uname -m
        switch -Wildcard ($uname_m) {
            "x86_64" { $Arch = "amd64" }
            "amd64" { $Arch = "amd64" }
            "arm64" { $Arch = "arm64" }
            "aarch64" { $Arch = "arm64" }
        }
    } catch {}
}

# Validate detection
if ($OS -eq "unknown" -or $Arch -eq "unknown") {
    Write-Error "Unable to detect platform (OS: $OS, Arch: $Arch)"
    Write-Host "Please manually run the appropriate binary from $BinDir"
    if (Test-Path $BinDir) {
        Get-ChildItem $BinDir | Select-Object -ExpandProperty Name
    } else {
        Write-Host "No binaries found in $BinDir"
    }
    exit 1
}

# Determine binary name
$ext = if ($OS -eq "windows") { ".exe" } else { "" }
$BinaryName = "latent-cli-$OS-$ARCH$ext"
$BinaryPath = Join-Path $BinDir $BinaryName

# Check if binary exists
if (-not (Test-Path $BinaryPath)) {
    Write-Error "Binary not found: $BinaryPath"
    Write-Host ""
    Write-Host "Available binaries:"
    if (Test-Path $BinDir) {
        Get-ChildItem $BinDir | Select-Object -ExpandProperty Name | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "  No binaries found in $BinDir"
    }
    Write-Host ""
    Write-Host "Your platform: $OS $ARCH"
    exit 1
}

# Run the binary with all passed arguments
& $BinaryPath @Arguments

# Exit with the binary's exit code
exit $LASTEXITCODE
