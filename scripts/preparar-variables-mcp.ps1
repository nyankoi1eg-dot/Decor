<#
.SYNOPSIS
  Prepara las variables de entorno de los servidores MCP de Google (GA4 y GTM)
  para pegarlas en los ajustes del entorno de Claude Code en la web.

.DESCRIPTION
  Lee las dos claves de servicio del disco, comprueba que son válidas, y va
  copiando al portapapeles cada valor de uno en uno para que lo pegues en el
  formulario sin errores de copiado.

  Todo ocurre en tu máquina. Nada se envía a ningún sitio y no se escribe
  ningún fichero nuevo con secretos dentro.

.EXAMPLE
  .\preparar-variables-mcp.ps1

.EXAMPLE
  .\preparar-variables-mcp.ps1 -Mostrar
  Imprime los valores en pantalla en vez de usar el portapapeles.
#>

[CmdletBinding()]
param(
    [string] $ClaveGA4 = "$env:USERPROFILE\OneDrive - DECORCENTER\Documentos\Claude GA\TOKENS\GA4\ga-claude-decorcenter-93536c518be6.json",
    [string] $ClaveGTM = "$env:USERPROFILE\OneDrive - DECORCENTER\Documentos\Claude GA\TOKENS\GTM\gtm-mcp-decorcenter-8226c6e281f9.json",
    [string] $PropertyIdGA4 = "276921254",
    [switch] $Mostrar
)

$ErrorActionPreference = 'Stop'

function Escribe-Titulo($texto) {
    Write-Host ""
    Write-Host "== $texto" -ForegroundColor Cyan
}

function Lee-ClaveDeServicio {
    param([string] $Ruta, [string] $Etiqueta)

    if (-not (Test-Path -LiteralPath $Ruta)) {
        throw "No encuentro la clave de $Etiqueta en:`n  $Ruta`nPásala con -Clave$Etiqueta 'C:\ruta\a\la\clave.json'"
    }

    $bytes = [IO.File]::ReadAllBytes($Ruta)

    # Comprobamos que es una clave de servicio de verdad antes de codificarla:
    # más vale descubrir aquí que el fichero es el que no era.
    try {
        $json = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
    } catch {
        throw "El fichero de $Etiqueta no es JSON válido:`n  $Ruta"
    }

    if ($json.type -ne 'service_account') {
        throw "El fichero de $Etiqueta no es una clave de cuenta de servicio (type = '$($json.type)')."
    }
    if (-not $json.private_key -or -not $json.client_email) {
        throw "A la clave de $Etiqueta le faltan campos (private_key / client_email)."
    }

    Write-Host "  cuenta   : $($json.client_email)" -ForegroundColor DarkGray
    Write-Host "  proyecto : $($json.project_id)" -ForegroundColor DarkGray

    return [Convert]::ToBase64String($bytes)
}

function Entrega-Valor {
    param([string] $Nombre, [string] $Valor, [switch] $Secreto)

    if ($Mostrar) {
        Write-Host ""
        Write-Host "$Nombre =" -ForegroundColor Yellow
        Write-Host $Valor
        return
    }

    Set-Clipboard -Value $Valor
    $long = $Valor.Length
    Write-Host ""
    Write-Host "  $Nombre" -ForegroundColor Yellow -NoNewline
    Write-Host " -> copiado al portapapeles ($long caracteres)"
    if ($Secreto) {
        Write-Host "  (es la clave privada: pégala solo en el formulario de variables de entorno)" -ForegroundColor DarkGray
    }
    Read-Host "  Pégalo en los ajustes del entorno y pulsa Enter para continuar" | Out-Null
}

Escribe-Titulo "Leyendo las claves de servicio"

Write-Host "GA4:" -ForegroundColor White
$ga4B64 = Lee-ClaveDeServicio -Ruta $ClaveGA4 -Etiqueta 'GA4'

Write-Host ""
Write-Host "GTM:" -ForegroundColor White
$gtmB64 = Lee-ClaveDeServicio -Ruta $ClaveGTM -Etiqueta 'GTM'

# Secreto compartido local entre el servidor GTM y .mcp.json. No es una
# credencial de Google: solo evita que el servidor quede abierto a cualquier
# proceso del contenedor.
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$apiKey = [Convert]::ToBase64String($bytes)

Escribe-Titulo "Variables a definir en los ajustes del entorno"
Write-Host "  claude.ai/code -> tu entorno -> Environment variables" -ForegroundColor DarkGray
Write-Host "  Las cuatro van en el MISMO entorno." -ForegroundColor DarkGray

Entrega-Valor -Nombre 'GA4_PROPERTY_ID'  -Valor $PropertyIdGA4
Entrega-Valor -Nombre 'GA4_SA_KEY_B64'   -Valor $ga4B64 -Secreto
Entrega-Valor -Nombre 'GTM_SA_KEY_B64'   -Valor $gtmB64 -Secreto
Entrega-Valor -Nombre 'GTM_MCP_API_KEY'  -Valor $apiKey -Secreto

if (-not $Mostrar) {
    # Un espacio, no cadena vacía: Set-Clipboard rechaza '' por validación.
    Set-Clipboard -Value ' '
    Write-Host ""
    Write-Host "Portapapeles vaciado." -ForegroundColor DarkGray
}

Escribe-Titulo "Falta un paso que no depende de esto"
Write-Host @"
  En tagmanager.google.com, contenedor GTM-ND7VH8Z6:
  Administrar -> Gestion de usuarios -> anadir

    gtm-mcp-decorcenter@gtm-mcp-decorcenter.iam.gserviceaccount.com

  con permiso de Lectura sobre la cuenta y el contenedor.
  Sin esto la clave es valida y aun asi todo responde 403.

  Despues, abre una sesion NUEVA: los servidores MCP se registran al arrancar.
"@
