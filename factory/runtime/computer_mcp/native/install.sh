#!/bin/bash
set -euo pipefail
source /opt/native/runtime/database.sh
profile=$(cat /opt/native/site-id)
install -d -m 750 -o www-data -g www-data /var/lib/native-data
install -d -m 755 /var/www/native
start_database /var/lib/mysql
mariadb <<'SQL'
CREATE DATABASE cua CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cua'@'localhost' IDENTIFIED BY 'cua-local';
GRANT ALL PRIVILEGES ON cua.* TO 'cua'@'localhost';
SQL
cd /opt/native/provision
bash ./install.sh
install -m 644 ./site.conf /etc/apache2/sites-enabled/100-native.conf
php ./project.php | python3 /opt/native/runtime/projection.py "/opt/cua/seed/$profile.json"
mkdir -p /var/www/cua-health
printf 'ready\n' > /var/www/cua-health/ready
printf 'Alias /__health /var/www/cua-health/ready\n<Directory /var/www/cua-health>\n Require all granted\n</Directory>\n' > /etc/apache2/conf-enabled/cua-health.conf
printf '<VirtualHost 127.0.0.1:443>\nServerName invalid.local\nSSLEngine on\nSSLCertificateFile /opt/cua/offline.crt\nSSLCertificateKeyFile /opt/cua/offline.key\n<Location />\nRequire all denied\n</Location>\n</VirtualHost>\n' > /etc/apache2/sites-enabled/000-reject.conf
apache2ctl configtest
mariadb-admin shutdown
mv /var/lib/mysql /opt/native/mysql-seed
mv /var/lib/native-data /opt/native/data-seed
chmod 700 /opt/native
