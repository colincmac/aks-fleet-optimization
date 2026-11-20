param(
    [Parameter(Mandatory)]
    [string] $OutputDir,

    [string] $Advisor = 'aks-fleet-advisor'
)

$ErrorActionPreference = 'Stop'
Get-Command $Advisor -CommandType Application | Out-Null
if (Test-Path -LiteralPath $OutputDir) {
    throw 'Choose a new report directory.'
}
$reports = New-Item -ItemType Directory -Path $OutputDir
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$fixtures = Join-Path $repo 'examples/fixtures'
$exampleClock = '2026-10-29T12:00:00Z'

$cases = [ordered]@{
    'AKS-RQ-001'    = @('missing-request-snapshot', 'baseline')
    'AKS-RQ-002'    = @('history-example/snapshot', 'guarded')
    'AKS-RQ-003'    = @('request-risk-snapshot', 'baseline')
    'AKS-MEM-001'   = @('oom-pack-snapshot', 'baseline')
    'AKS-MEM-002'   = @('memory-safety-pack-snapshot', 'baseline')
    'AKS-MEM-003'   = @('memory-request-pack-snapshot', 'guarded')
    'AKS-MEM-004'   = @('pod-memory-pack-snapshot', 'baseline')
    'AKS-MEM-005'   = @('memory-limit-pack-snapshot', 'guarded')
    'AKS-AS-001'    = @('fixed-replica-pack-snapshot', 'baseline')
    'AKS-AS-002'    = @('interaction-pack-snapshot', 'baseline')
    'AKS-AS-003'    = @('hpa-pinning-pack-snapshot', 'baseline')
    'AKS-AS-004'    = @('keda-pack-snapshot', 'baseline')
    'AKS-AS-005'    = @('hpa-floor-pack-snapshot', 'guarded')
    'AKS-AS-006'    = @('hpa-change-pack-snapshot', 'baseline')
    'AKS-AS-007'    = @('vpa-bounds-pack-snapshot', 'baseline')
    'AKS-REL-001'   = @('restart-pack-snapshot', 'baseline')
    'AKS-REL-002'   = @('termination-pack-snapshot', 'baseline')
    'AKS-REL-003'   = @('eviction-pack-snapshot', 'baseline')
    'AKS-SCHED-001' = @('scheduling-review-snapshot', 'baseline')
    'AKS-SCHED-002' = @('optimization-constraints-snapshot', 'baseline')
    'AKS-NP-001'    = @('pool-review-snapshot', 'baseline')
    'AKS-NP-002'    = @('capacity-review-snapshot', 'baseline')
    'AKS-NP-003'    = @('capacity-review-snapshot', 'baseline')
    'AKS-NP-004'    = @('daemonset-overhead-snapshot', 'baseline')
    'AKS-START-001' = @('startup-snapshot', 'baseline')
}

$PSNativeCommandUseErrorActionPreference = $false
foreach ($pack in $cases.Keys) {
    $snapshotName, $mode = $cases[$pack]
    $inputRoot = if ($snapshotName -like 'history-example/*') { $repo } else { $fixtures }
    $snapshot = Join-Path $inputRoot "$snapshotName.json"
    $report = Join-Path $reports.FullName "$pack.md"
    & $Advisor analyze --snapshot $snapshot --pack $pack --mode $mode --as-of $exampleClock --format markdown --output $report
    if ($LASTEXITCODE -notin @(0, 3) -or -not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw "Offline replay for $pack failed with exit $LASTEXITCODE."
    }
    "$pack $mode (exit $LASTEXITCODE): $report"
}