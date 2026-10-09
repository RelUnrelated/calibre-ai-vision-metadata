$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $projectRoot ('.calibre-smoke-' + [guid]::NewGuid().ToString('N'))
$savedConfig = $env:CALIBRE_CONFIG_DIRECTORY
$savedTemp = $env:CALIBRE_TEMP_DIR
$savedPreview = $env:AI_METADATA_SMOKE_PREVIEW
$testExitCode = 1
New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
try {
    $env:CALIBRE_CONFIG_DIRECTORY = $runtimeRoot
    $env:CALIBRE_TEMP_DIR = $runtimeRoot
    $env:AI_METADATA_SMOKE_PREVIEW = ''
    & calibre-debug -e (Join-Path $PSScriptRoot 'calibre_smoke.py')
    $testExitCode = $LASTEXITCODE
} finally {
    $env:CALIBRE_CONFIG_DIRECTORY = $savedConfig
    $env:CALIBRE_TEMP_DIR = $savedTemp
    $env:AI_METADATA_SMOKE_PREVIEW = $savedPreview
    $resolvedRuntime = (Resolve-Path -LiteralPath $runtimeRoot).Path
    if ((Split-Path -Parent $resolvedRuntime) -ne $projectRoot -or
        (Split-Path -Leaf $resolvedRuntime) -notlike '.calibre-smoke-*') {
        throw 'Refusing to remove a test directory outside the project root.'
    }
    Remove-Item -LiteralPath $resolvedRuntime -Recurse -Force
}
exit $testExitCode
