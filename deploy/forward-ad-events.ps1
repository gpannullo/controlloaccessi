<# Run on each DC through Task Scheduler, every minute, no overlapping runs.
   Requires permission to read Security; config/state folder ACL restricted to task identity.
   State advances only after all HTTP batches have been acknowledged. #>
param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if (([uri]$cfg.endpoint).Scheme -ne 'https' -or $cfg.secret.Length -lt 32) { throw 'HTTPS and secret >=32 characters required' }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$statePath = "$ConfigPath.state"
$lock = [IO.File]::Open("$ConfigPath.lock", 'OpenOrCreate', 'ReadWrite', 'None')
try {
    $until = [DateTime]::UtcNow.AddSeconds(-2)
    $since = $until.AddMinutes(-15)
    if (Test-Path -LiteralPath $statePath) { $since = [DateTime]::Parse((Get-Content -LiteralPath $statePath -Raw)).ToUniversalTime().AddMinutes(-2) }
    # Limit catch-up to 15-minute windows without skipping backlog.
    if ($until -gt $since.AddMinutes(15)) { $until = $since.AddMinutes(15) }
    try { $events = @(Get-WinEvent -FilterHashtable @{LogName='Security'; StartTime=$since; EndTime=$until} -Oldest -ErrorAction Stop) }
    catch { if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { $events = @() } else { throw } }
    $batch = @()
    function Send-Batch($rows) {
        $body = [Text.Encoding]::UTF8.GetBytes((@{events=@($rows)} | ConvertTo-Json -Depth 8 -Compress))
        if ($body.Length -gt 1048576) { throw 'Batch exceeds 1 MiB; reduce batch size' }
        $stamp = [string][long]([DateTime]::UtcNow - [DateTime]'1970-01-01').TotalSeconds
        $prefix = [Text.Encoding]::UTF8.GetBytes("$stamp.")
        $signed = New-Object byte[] ($prefix.Length + $body.Length)
        [Array]::Copy($prefix,0,$signed,0,$prefix.Length)
        [Array]::Copy($body,0,$signed,$prefix.Length,$body.Length)
        $mac = New-Object Security.Cryptography.HMACSHA256
        try { $mac.Key = [Text.Encoding]::UTF8.GetBytes($cfg.secret); $signature = ([BitConverter]::ToString($mac.ComputeHash($signed))).Replace('-','').ToLowerInvariant() } finally { $mac.Dispose() }
        $response = Invoke-RestMethod -Method Post -Uri $cfg.endpoint -ContentType 'application/json' -Body $body -TimeoutSec 60 -Headers @{'X-AD-Source'=$cfg.source; 'X-AD-Timestamp'=$stamp; 'X-AD-Signature'=$signature}
        if ($response.received -ne $rows.Count) { throw 'Incomplete acknowledgement' }
    }
    foreach ($event in $events) {
        [xml]$xml = $event.ToXml()
        $data = @{}
        foreach ($field in $xml.Event.EventData.Data) { if ($field.Name) { $data[[string]$field.Name] = [string]$field.'#text' } }
        # 1102 can use UserData rather than EventData.
        if ($xml.Event.UserData) { foreach ($field in $xml.Event.UserData.ChildNodes.ChildNodes) { if ($field.LocalName) { $data[$field.LocalName] = $field.InnerText } } }
        $batch += @{event_id=$event.Id; record_id=$event.RecordId; computer=$event.MachineName; time=$event.TimeCreated.ToUniversalTime().ToString('o'); data=$data}
        if ($batch.Count -ge 50) { Send-Batch $batch; $batch = @() }
    }
    if ($batch.Count) { Send-Batch $batch }
    [IO.File]::WriteAllText("$statePath.tmp", $until.ToString('o'))
    Move-Item -LiteralPath "$statePath.tmp" -Destination $statePath -Force
    Write-Output "Acknowledged $($events.Count) events through $($until.ToString('o'))"
} finally { $lock.Dispose() }
