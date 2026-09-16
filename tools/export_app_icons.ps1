param(
    [string]$Config = (Join-Path $PSScriptRoot '..\config.json')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if (-not ('SoomfonIconExport' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class SoomfonIconExport {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, EntryPoint = "SHDefExtractIconW")]
    public static extern int Extract(string file, int index, uint flags,
        out IntPtr large, out IntPtr small, uint size);
    [DllImport("user32.dll")]
    public static extern bool DestroyIcon(IntPtr icon);
}
'@
}

$configPath = (Resolve-Path -LiteralPath $Config).Path
$base = Split-Path -Parent $configPath
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$iconDirectory = Join-Path $base 'icons'
New-Item -ItemType Directory -Path $iconDirectory -Force | Out-Null

foreach ($property in $settings.buttons.PSObject.Properties) {
    $key = [int]$property.Name
    $button = $property.Value
    if ($key -gt 5 -or -not $button.app) { continue }
    $executable = [Environment]::ExpandEnvironmentVariables($button.app.command[0])
    $appFolderArgument = $button.app.command | Where-Object { $_ -like 'shell:AppsFolder\*' } | Select-Object -First 1
    if ($appFolderArgument) {
        $appId = $appFolderArgument.Substring('shell:AppsFolder\'.Length)
        $family, $entryId = $appId -split '!', 2
        $package = Get-AppxPackage | Where-Object PackageFamilyName -eq $family | Select-Object -First 1
        if (-not $package) { throw "Packaged app not found for $($button.label): $family. Run as your normal Windows user." }
        $manifest = Get-AppxPackageManifest -Package $package.PackageFullName
        $entry = $manifest.Package.Applications.Application | Where-Object Id -eq $entryId | Select-Object -First 1
        if (-not $entry.Executable) { throw "No executable found for $appId" }
        $executable = Join-Path $package.InstallLocation $entry.Executable
    } elseif (-not [IO.Path]::IsPathRooted($executable)) {
        if ($executable.Contains('/') -or $executable.Contains('\')) {
            $executable = Join-Path $base $executable
        } else {
            $executable = (Get-Command $executable -CommandType Application).Source
        }
    }
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw "Executable not found: $executable" }
    $large = [IntPtr]::Zero
    $small = [IntPtr]::Zero
    $icon = $null
    $bitmap = $null
    try {
        $result = [SoomfonIconExport]::Extract($executable, 0, 0, [ref]$large, [ref]$small, 64)
        if ($result -ne 0 -or $large -eq [IntPtr]::Zero) { throw "Cannot extract icon from $executable (HRESULT $result)" }
        $icon = [Drawing.Icon]::FromHandle($large)
        $bitmap = $icon.ToBitmap()
        $relative = "icons/button-$key.png"
        $bitmap.Save((Join-Path $base $relative), [Drawing.Imaging.ImageFormat]::Png)
        $button | Add-Member -NotePropertyName icon -NotePropertyValue $relative -Force
        Write-Output "Exported $($button.label) -> $relative"
    } finally {
        if ($bitmap) { $bitmap.Dispose() }
        if ($icon) { $icon.Dispose() }
        if ($large -ne [IntPtr]::Zero) { [SoomfonIconExport]::DestroyIcon($large) | Out-Null }
        if ($small -ne [IntPtr]::Zero) { [SoomfonIconExport]::DestroyIcon($small) | Out-Null }
    }
}

$settings | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding utf8
Write-Output "Updated $configPath"
