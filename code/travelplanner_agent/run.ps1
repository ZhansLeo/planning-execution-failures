param(
    [ValidateSet('inspect', 'sample', 'tool', 'contract', 'phase1', 'direct', 'react', 'planner-react', 'verifier-replan', 'dev', 'evaluate', 'pilot', 'batch', 'aggregate', 'compare')]
    [string]$Command = 'phase1',
    [string]$OfficialRepo = $(if ($env:TRAVELPLANNER_OFFICIAL_REPO) { $env:TRAVELPLANNER_OFFICIAL_REPO } else { '../TravelPlanner' }),
    [string]$Artifacts = "$PSScriptRoot/artifacts",
    [string]$RunsDir = "$PSScriptRoot/runs",
    [string]$Model = '',
    [string]$BaseUrl = '',
    [string]$RunDir = '',
    [string]$ExperimentId = '',
    [string]$ExperimentDir = '',
    [ValidateSet('direct', 'react', 'planner-react', 'verifier-replan')]
    [string]$Baseline = 'direct',
    [ValidateSet('train', 'validation')]
    [string]$Split = 'validation',
    [string]$StageADir = '',
    [string]$StageBDir = '',
    [string]$StageCDir = '',
    [string]$StageDDir = '',
    [switch]$Resume,
    [switch]$OfficialAggregate,
    [int]$Index = 0,
    [int]$Start = 0,
    [int]$End = 0
)

$env:PYTHONPATH = "$PSScriptRoot/src"
$arguments = @('-m', 'travelplanner_agent', $Command, '--official-repo', $OfficialRepo, '--artifacts', $Artifacts, '--runs-dir', $RunsDir)
if ($Index -gt 0) { $arguments += @('--index', $Index) }
if ($Start -gt 0) { $arguments += @('--start', $Start) }
if ($End -gt 0) { $arguments += @('--end', $End) }
if ($Model) { $arguments += @('--model', $Model) }
if ($BaseUrl) { $arguments += @('--base-url', $BaseUrl) }
if ($RunDir) { $arguments += @('--run-dir', $RunDir) }
if ($ExperimentId) { $arguments += @('--experiment-id', $ExperimentId) }
if ($ExperimentDir) { $arguments += @('--experiment-dir', $ExperimentDir) }
if ($Resume) { $arguments += '--resume' }
if ($OfficialAggregate) { $arguments += '--official-aggregate' }
if ($Baseline) { $arguments += @('--baseline', $Baseline) }
if ($Split) { $arguments += @('--split', $Split) }
if ($StageADir) { $arguments += @('--stage-a-dir', $StageADir) }
if ($StageBDir) { $arguments += @('--stage-b-dir', $StageBDir) }
if ($StageCDir) { $arguments += @('--stage-c-dir', $StageCDir) }
if ($StageDDir) { $arguments += @('--stage-d-dir', $StageDDir) }
conda run -n llm-learning python @arguments
exit $LASTEXITCODE
