param(
    [string]$IdentityFile = '',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$branch = 'develop/v0.4'
$servers = @('192.168.15.26', '192.168.15.24')
function Git-Checked([string[]]$Arguments) {
    $result = & git -C $repo @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Git fallito: $Arguments" }
    return $result
}
try {
    Get-Command git, ssh -ErrorAction Stop | Out-Null
    if ($IdentityFile -and !(Test-Path -LiteralPath $IdentityFile -PathType Leaf)) { throw 'Chiave SSH non trovata.' }
    if (Git-Checked @('status','--porcelain','--untracked-files=all')) { throw 'Copia locale non pulita: completare commit e push prima del deploy.' }
    if ((Git-Checked @('branch','--show-current')) -ne $branch) { throw "Selezionare il branch $branch nella copia locale." }
    Git-Checked @('fetch','origin',$branch)
    $commit = Git-Checked @('rev-parse','HEAD')
    if ($commit -ne (Git-Checked @('rev-parse',"origin/$branch"))) { throw 'HEAD locale diverso dal branch remoto: completare push/allineamento.' }
    $script = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'deploy-server.sh')).Replace("`r`n","`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    $sshArgs = @('-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15')
    if ($IdentityFile) { $sshArgs += @('-i',$IdentityFile,'-o','IdentitiesOnly=yes') }
    function Invoke-Deploy([string]$Server, [string]$Mode) {
        Write-Host "=== $Server : $Mode : $commit ==="
        $remote = "printf '%s' '$encoded' | base64 -d | bash -s -- '$Mode' '$commit'"
        & ssh @sshArgs "controlloaccessi@$Server" $remote
        if ($LASTEXITCODE -ne 0) { throw "Operazione $Mode fallita su $Server. Distribuzione interrotta." }
    }
    foreach ($server in $servers) { Invoke-Deploy $server 'check' }
    if (!$CheckOnly) {
        foreach ($server in $servers) { Invoke-Deploy $server 'deploy' }
        Write-Host "Deploy completato su entrambi i server: $commit"
    } else { Write-Host 'Controlli completati. Nessuna installazione eseguita.' }
    exit 0
} catch {
    Write-Error -Message $_ -ErrorAction Continue
    exit 1
}
