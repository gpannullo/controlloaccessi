#!/bin/bash
set -euo pipefail

DB_NAME="controlloaccessi"
LOCAL_DB="/var/backups/controlloaccessi/postgresql"
NAS_MOUNT="/mnt/backup-controlloaccessi"
NAS_ROOT="${NAS_MOUNT}/ControlloAccessi"
NAS_DB="${NAS_ROOT}/database"
NAS_APP="${NAS_ROOT}/application"
NAS_CONFIG="${NAS_ROOT}/configuration"
APP_ROOT="/var/www/controlloaccessi/app"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
DB_FILE="${DB_NAME}_${DATE}.dump"
APP_FILE="controlloaccessi_app_${DATE}.tar.gz"
CONFIG_FILE="controlloaccessi_config_${DATE}.tar.gz"
NAS_RETENTION_DAYS="${NAS_RETENTION_DAYS:-60}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }
mkdir -p "${LOCAL_DB}"
log "Avvio backup ControlloAccessi"

sudo -u postgres pg_dump --format=custom --file="${LOCAL_DB}/${DB_FILE}" "${DB_NAME}"
chmod 600 "${LOCAL_DB}/${DB_FILE}"
sudo -u postgres pg_restore --list "${LOCAL_DB}/${DB_FILE}" > /dev/null

tar --exclude="${APP_ROOT}/staticfiles" --exclude="${APP_ROOT}/__pycache__" --exclude="*.pyc" --exclude=".git" \
    -czf "/tmp/${APP_FILE}" -C "/var/www/controlloaccessi" app
tar -czf "/tmp/${CONFIG_FILE}" /etc/controlloaccessi.env /etc/nginx/sites-available/controlloaccessi \
    /etc/systemd/system/controlloaccessi.service /etc/systemd/system/controlloaccessi-backup.service \
    /etc/systemd/system/controlloaccessi-backup.timer 2>/dev/null || true
chmod 600 "/tmp/${CONFIG_FILE}"

if ! mountpoint -q "${NAS_MOUNT}"; then
    log "ERRORE: NAS non montato su ${NAS_MOUNT}"
    rm -f "/tmp/${APP_FILE}" "/tmp/${CONFIG_FILE}"
    exit 1
fi

mkdir -p "${NAS_DB}" "${NAS_APP}" "${NAS_CONFIG}"
cp "${LOCAL_DB}/${DB_FILE}" "${NAS_DB}/${DB_FILE}"
cp "/tmp/${APP_FILE}" "${NAS_APP}/${APP_FILE}"
cp "/tmp/${CONFIG_FILE}" "${NAS_CONFIG}/${CONFIG_FILE}"
test -s "${NAS_DB}/${DB_FILE}" && test -s "${NAS_APP}/${APP_FILE}" && test -s "${NAS_CONFIG}/${CONFIG_FILE}"
log "Copie NAS verificate"

find "${NAS_DB}" -type f -name "${DB_NAME}_*.dump" -mtime +"${NAS_RETENTION_DAYS}" -delete
find "${NAS_APP}" -type f -name "controlloaccessi_app_*.tar.gz" -mtime +"${NAS_RETENTION_DAYS}" -delete
find "${NAS_CONFIG}" -type f -name "controlloaccessi_config_*.tar.gz" -mtime +"${NAS_RETENTION_DAYS}" -delete

# Mantiene il dump locale corrente come fallback e rimuove i precedenti
# soltanto dopo la verifica positiva delle copie sul NAS.
find "${LOCAL_DB}" -type f -name "${DB_NAME}_*.dump" ! -name "${DB_FILE}" -delete
rm -f "/tmp/${APP_FILE}" "/tmp/${CONFIG_FILE}"
log "Backup completato: conservato localmente solo ${DB_FILE}"
