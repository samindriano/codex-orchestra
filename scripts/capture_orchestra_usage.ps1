[CmdletBinding()]
param(
    [string]$StorePath = "",
    [string]$Branch = "codex/orchestra-telemetry-snapshots"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$snapshotDir = Join-Path $repoRoot "snapshots"
$snapshotFiles = @(
    "snapshots/orchestra-usage-latest.json",
    "snapshots/orchestra-usage-latest.md"
)

function Invoke-Git([string[]]$Arguments) {
    & git -C $repoRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git failed: $($Arguments -join ' ')"
    }
}

$top = (& git -C $repoRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or (Resolve-Path $top).Path -ne $repoRoot) {
    throw "The script is not running from the expected repository root."
}

$currentBranch = (& git -C $repoRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $Branch) {
    throw "Refusing to publish from branch '$currentBranch'. Expected '$Branch'."
}

$stagedBefore = @(& git -C $repoRoot diff --cached --name-only)
if ($stagedBefore.Count -gt 0) {
    throw "Refusing to publish while unrelated staged changes exist."
}

$snapshotChangesBefore = @(& git -C $repoRoot status --porcelain -- $snapshotFiles)
if ($snapshotChangesBefore.Count -gt 0) {
    throw "Refusing to overwrite pre-existing changes under snapshots/."
}

if ([string]::IsNullOrWhiteSpace($StorePath)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_ORCHESTRA_STORE)) {
        $StorePath = $env:CODEX_ORCHESTRA_STORE
    } elseif (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        $StorePath = Join-Path $env:CODEX_HOME "orchestra-telemetry"
    } else {
        $StorePath = Join-Path $env:USERPROFILE ".codex\orchestra-telemetry"
    }
}
$storeResolved = (Resolve-Path $StorePath -ErrorAction Stop).Path
if (-not (Test-Path (Join-Path $storeResolved "ledger.jsonl") -PathType Leaf)) {
    throw "Telemetry ledger was not found under the selected local store."
}

& python (Join-Path $repoRoot "scripts\orchestra_review_snapshot.py") --store $storeResolved --output-dir $snapshotDir
if ($LASTEXITCODE -ne 0) {
    throw "Snapshot generation failed; nothing was committed or pushed."
}

$snapshotChanges = @(& git -C $repoRoot status --porcelain -- $snapshotFiles)
if ($snapshotChanges.Count -eq 0) {
    Write-Output "Snapshot unchanged; nothing to commit or push."
    exit 0
}

Invoke-Git ((@("diff", "--check", "--") + $snapshotFiles))
Invoke-Git ((@("add", "--") + $snapshotFiles))
$stagedAfter = @(& git -C $repoRoot diff --cached --name-only)
$unexpected = @($stagedAfter | Where-Object { $_ -notin $snapshotFiles })
if ($unexpected.Count -gt 0 -or $stagedAfter.Count -ne $snapshotFiles.Count) {
    throw "Refusing to commit: staged paths were not exactly the two snapshot files."
}
Invoke-Git ((@("diff", "--cached", "--check", "--")))

$captureTime = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Invoke-Git ((@("commit", "-m", "chore(telemetry): update Orchestra usage snapshot $captureTime")))
Invoke-Git ((@("push", "origin", $Branch)))
Write-Output "Published sanitized Orchestra usage snapshot to origin/$Branch."
