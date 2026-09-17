# Installe l'environnement Python du moteur de detection des doublons fournisseurs.
#
# Usage (une fois par poste, apres avoir copie le dossier doublons-fournisseurs
# dans %USERPROFILE%\.claude\skills\) :
#
#   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\doublons-fournisseurs\moteur\installer.ps1"
#
# Ce script cree un environnement virtuel Python isole (moteur\.venv) et y
# installe les deux seules dependances du moteur (pandas, openpyxl). Il ne
# touche a rien d'autre sur le poste. Toute issue autre que la derniere
# ligne "Installation terminee" est un echec : ne pas utiliser les resultats.

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $racine ".venv"
$exigences = Join-Path $racine "requirements.txt"

function Trouver-Python {
    foreach ($commande in @("python", "python3")) {
        $cmd = Get-Command $commande -ErrorAction SilentlyContinue
        if ($cmd) {
            $version = & $commande --version 2>&1
            if ($version -match "Python 3\.(\d+)") {
                if ([int]$Matches[1] -ge 9) {
                    return $commande
                }
            }
        }
    }
    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        return "py -3"
    }
    return $null
}

Write-Host "Recherche d'un interpreteur Python (3.9 ou plus)..."
$python = Trouver-Python
if (-not $python) {
    Write-Host ""
    Write-Host "Python introuvable sur ce poste." -ForegroundColor Red
    Write-Host "Installer Python 3 via le portail logiciel de l'entreprise ou le Microsoft Store, puis relancer ce script."
    exit 1
}
Write-Host "Interpreteur retenu : $python"

if (Test-Path $venv) {
    Write-Host "Environnement virtuel existant detecte, reinstallation propre..."
    Remove-Item -Recurse -Force $venv
}

Write-Host "Creation de l'environnement virtuel..."
Invoke-Expression "$python -m venv `"$venv`""
if ($LASTEXITCODE -ne 0) {
    Write-Host "Echec de la creation de l'environnement virtuel." -ForegroundColor Red
    exit 1
}

$pip = Join-Path $venv "Scripts\pip.exe"
$pythonVenv = Join-Path $venv "Scripts\python.exe"

Write-Host "Installation des dependances (pandas, openpyxl)..."
& $pip install --upgrade pip --quiet
& $pip install -r $exigences --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Echec de l'installation des dependances." -ForegroundColor Red
    exit 1
}

Write-Host "Verification de l'installation (tests unitaires du moteur)..."
Push-Location $racine
& $pythonVenv -m pytest tests -q
$testsOk = $LASTEXITCODE -eq 0
Pop-Location

if (-not $testsOk) {
    Write-Host "Les tests du moteur echouent apres installation : ne pas utiliser les resultats." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Installation terminee"
