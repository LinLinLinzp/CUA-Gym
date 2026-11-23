#!/bin/bash
start_database() {
  install -d -m 755 -o mysql -g mysql /run/mysqld
  rm -f /run/mysqld/mysqld.sock /run/mysqld/mysqld.pid
  mariadbd --user=mysql --datadir="$1" --skip-networking --socket=/run/mysqld/mysqld.sock \
    --pid-file=/run/mysqld/mysqld.pid --innodb-buffer-pool-size=96M --innodb-log-file-size=32M \
    --log-error=/run/mysqld/native.log &
  local pid=$!
  for _ in $(seq 1 200); do
    if mariadb-admin --protocol=socket ping --silent >/dev/null 2>&1; then return; fi
    if ! kill -0 "$pid"; then cat /run/mysqld/native.log >&2; return 1; fi
    sleep 0.1
  done
  cat /run/mysqld/native.log >&2
  return 1
}
