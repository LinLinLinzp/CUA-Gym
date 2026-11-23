#!/bin/bash
set -euo pipefail
umask 022
source /opt/native/runtime/database.sh
# These two directories belong to this isolated desktop and are regenerated on every native boot.
rm -rf -- /run/cua-native-db /var/lib/native-data
cp -a /opt/native/mysql-seed /run/cua-native-db
cp -a /opt/native/data-seed /var/lib/native-data
start_database /run/cua-native-db
export APACHE_CONFDIR=/etc/apache2
source /etc/apache2/envvars
install -d -m 755 /run/apache2/ /var/lock/apache2
rm -f "$APACHE_PID_FILE"
/usr/sbin/apache2 -DFOREGROUND &
