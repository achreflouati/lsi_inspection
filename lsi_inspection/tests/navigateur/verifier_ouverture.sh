#!/bin/bash
# Test navigateur : ouvrir un document enregistré ne doit jamais le modifier (frm.is_dirty() == false).
# Usage : verifier_ouverture.sh <Doctype> <nom>   (site tic.erpsys.ovh)
# Prérequis (hors dépôt, sans sudo) : Chromium Playwright + bibliothèques extraites dans $LSI_NAVIGATEUR
#   npm install playwright-core@1.47.2 ; PLAYWRIGHT_BROWSERS_PATH=$LSI_NAVIGATEUR/browsers npx playwright@1.47.2 install chromium
#   apt-get download libnss3 libnspr4 libasound2 ; dpkg-deb -x <deb> $LSI_NAVIGATEUR/libs
# Une session Administrator temporaire est créée puis supprimée ; le document n'est jamais enregistré.
set -u
N=${LSI_NAVIGATEUR:?définir LSI_NAVIGATEUR}
ICI=$(cd "$(dirname "$0")" && pwd)
BENCH=/home/frappe/frappe-bench
export LD_LIBRARY_PATH=$(find "$N/libs" -name "*.so*" -printf "%h\n" | sort -u | tr '\n' ':')
SID=$(cd $BENCH && ./env/bin/python "$ICI/session_temporaire.py" ouvrir | tail -1)
NODE_PATH="$N/node_modules" node "$ICI/ouvrir_sans_modifier.js" "$(ls -d $N/browsers/chromium-*/chrome-linux/chrome | head -1)" "$SID" "$1" "$2"
CODE=$?
(cd $BENCH && ./env/bin/python "$ICI/session_temporaire.py" fermer "$SID")
exit $CODE
