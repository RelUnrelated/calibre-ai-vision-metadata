$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$dist = Join-Path $root 'dist'
$zip = Join-Path $dist 'MetaManga_v1.0.0.zip'
New-Item -ItemType Directory -Path $dist -Force | Out-Null
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

$files = @(
    '__init__.py', 'main.py', 'ui.py', 'config.py', 'filename_parser.py',
    'result_schema.py', 'metadata_writer.py', 'filename_roles.py', 'about.txt',
    'plugin-import-name-ai_vision_metadata.txt', 'LICENSE.md', 'THIRD_PARTY_NOTICES.md'
)
$files += Get-ChildItem -LiteralPath (Join-Path $root 'images') -File | ForEach-Object { Join-Path 'images' $_.Name }
$files += Get-ChildItem -LiteralPath (Join-Path $root 'translations') -File -Filter '*.mo' -ErrorAction SilentlyContinue | ForEach-Object { Join-Path 'translations' $_.Name }

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$archive = [System.IO.Compression.ZipFile]::Open($zip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $files) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, (Join-Path $root $file), $file.Replace('\', '/'),
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
} finally {
    $archive.Dispose()
}
Write-Output "Built $zip"
