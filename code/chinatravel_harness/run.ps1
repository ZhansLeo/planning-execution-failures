param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$python = Join-Path $PSScriptRoot "..\ChinaTravel\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "ChinaTravel Python environment not found: $python" }
$env:PYTHONPATH = (Join-Path $PSScriptRoot "src")
& $python -m ct_harness.cli @Arguments
exit $LASTEXITCODE
