# Gera o APK do Marco 3 (app com Bluetooth e assinatura).
#
#   cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\marco-03"
#   powershell -ExecutionPolicy Bypass -File .\gerar-apk.ps1
#
# A compilação nativa (CMake/NDK) quebra com espaço e acento no caminho, então
# o app é espelhado em C:\presenca-m3 e compilado lá. O APK final volta para
# esta pasta: marco-03\presenca-m3.apk
#
# Primeira vez: 15 a 30 min (o Gradle baixa o que falta). Depois, bem menos.

$ErrorActionPreference = 'Stop'
$origem  = Join-Path $PSScriptRoot 'app'
$destino = 'C:\presenca-m3'
$apk     = Join-Path $PSScriptRoot 'presenca-m3.apk'

if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = 'C:\Android\sdk' }
$env:CI = '1'   # sem perguntas interativas do Expo

Write-Host '1/4  Copiando o app para' $destino
# Só a pasta android/ do próprio app (gerada pelo prebuild); as de node_modules ficam.
robocopy $origem $destino /MIR /XD (Join-Path $origem 'android') (Join-Path $origem '.expo') (Join-Path $destino 'android') /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy falhou ($LASTEXITCODE)" }

Push-Location $destino
try {
  Write-Host '2/4  Gerando o projeto Android (expo prebuild)'
  # Sem --clean: reaproveita a compilação nativa anterior (bem mais rápido).
  # Se der erro estranho, apague C:\presenca-m3\android e rode de novo.
  npx expo prebuild --platform android
  if ($LASTEXITCODE -ne 0) { throw 'expo prebuild falhou' }

  Write-Host '3/4  Compilando (Gradle) - demora'
  Push-Location android
  # Só arm64-v8a: é a arquitetura de praticamente todo celular atual e corta o tempo.
  .\gradlew.bat assembleRelease -PreactNativeArchitectures=arm64-v8a --no-daemon
  if ($LASTEXITCODE -ne 0) { throw 'Gradle falhou' }
  Pop-Location

  Write-Host '4/4  Copiando o APK'
  Copy-Item 'android\app\build\outputs\apk\release\app-release.apk' $apk -Force
}
finally {
  Pop-Location
}

Write-Host ''
Write-Host "APK pronto: $apk"
Write-Host 'Mande para o celular (cabo, Drive, WhatsApp...) e toque nele para instalar.'
