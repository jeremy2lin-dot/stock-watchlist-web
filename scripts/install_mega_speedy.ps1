param(
  [Parameter(Mandatory = $true)]
  [string]$SourcePath,

  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,

  [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'

function Resolve-SdkRoot {
  param([string]$Path)

  $item = Get-Item -LiteralPath $Path
  if ($item.PSIsContainer) {
    return $item.FullName
  }

  if ($item.Extension -notin @('.zip')) {
    throw "SourcePath must be a Mega Speedy SDK folder or .zip file. Got: $($item.Extension)"
  }

  $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mega_speedy_sdk_" + [System.Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tempRoot | Out-Null
  Expand-Archive -LiteralPath $item.FullName -DestinationPath $tempRoot -Force
  return $tempRoot
}

function Find-RequiredPath {
  param(
    [string]$Root,
    [string]$Name,
    [switch]$Directory
  )

  $matches = Get-ChildItem -LiteralPath $Root -Recurse -Force |
    Where-Object {
      $_.Name -eq $Name -and ($(if ($Directory) { $_.PSIsContainer } else { -not $_.PSIsContainer }))
    }

  if (-not $matches) {
    throw "Cannot find required SDK item: $Name"
  }
  return $matches[0].FullName
}

$sdkRoot = Resolve-SdkRoot -Path $SourcePath
$megaSpeedy = Find-RequiredPath -Root $sdkRoot -Name 'megaSpeedy' -Directory
$temp = Find-RequiredPath -Root $sdkRoot -Name 'Temp' -Directory
$config = Find-RequiredPath -Root $sdkRoot -Name 'speedyAPI_config.json'

Copy-Item -LiteralPath $megaSpeedy -Destination (Join-Path $ProjectRoot 'megaSpeedy') -Recurse -Force
Copy-Item -LiteralPath $temp -Destination (Join-Path $ProjectRoot 'Temp') -Recurse -Force
Copy-Item -LiteralPath $config -Destination (Join-Path $ProjectRoot 'speedyAPI_config.json') -Force

Write-Host "Copied Mega Speedy SDK files to $ProjectRoot"

& $Python -B -c "import importlib.util; spec = importlib.util.find_spec('megaSpeedy.spdQuoteAPI'); print('megaSpeedy.spdQuoteAPI', 'OK' if spec else 'NOT_FOUND')"
