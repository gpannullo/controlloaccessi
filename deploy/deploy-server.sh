#!/usr/bin/env bash
set -Eeuo pipefail
mode=${1:?Modalita mancante}
expected=${2:?Commit mancante}
[[ "$mode" == check || "$mode" == deploy ]]
[[ "$expected" =~ ^[0-9a-f]{40}$ ]]
cd /var/www/controlloaccessi/app
exec 9>/var/www/controlloaccessi/.deploy.lock
flock -n 9 || { echo 'Altro deploy in corso'; exit 1; }
trap 'echo "ERRORE alla riga $LINENO. Non viene eseguito rollback automatico del database." >&2' ERR
[[ "$(git branch --show-current)" == develop/v0.5 ]]
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    echo 'Repository server non pulito. Allineare le modifiche prima del deploy:'
    git status --short
    exit 1
fi
git fetch origin develop/v0.5
[[ "$(git rev-parse origin/develop/v0.5)" == "$expected" ]] || { echo 'Il branch remoto e cambiato. Ripetere dalla copia locale aggiornata.'; exit 1; }
git merge-base --is-ancestor HEAD "$expected"
test -r /etc/controlloaccessi.env
test -x /var/www/controlloaccessi/venv/bin/python
sudo -n -l /usr/bin/systemctl restart controlloaccessi >/dev/null
if [[ "$mode" == check ]]; then echo 'Preflight OK'; exit 0; fi
previous=$(git rev-parse HEAD)
echo "Commit precedente: $previous"
git pull --ff-only origin develop/v0.5
[[ "$(git rev-parse HEAD)" == "$expected" ]] || { echo 'Commit inatteso: servizio non riavviato'; exit 1; }
set -a
. /etc/controlloaccessi.env
set +a
py=/var/www/controlloaccessi/venv/bin/python
echo 'Verifica e installazione dipendenze...'
"$py" -m pip --disable-pip-version-check install --quiet --progress-bar off -r requirements.txt
"$py" manage.py check
"$py" manage.py migrate --plan
"$py" manage.py migrate --noinput
"$py" manage.py collectstatic --noinput
sudo -n /usr/bin/systemctl restart controlloaccessi
sleep 2
systemctl is-active --quiet controlloaccessi
echo "OK: $expected (precedente $previous)"
