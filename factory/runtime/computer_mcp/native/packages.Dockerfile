RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
 && chmod 755 /usr/sbin/policy-rc.d \
 && apt-get -o Acquire::Retries=3 update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      apache2 libapache2-mod-php8.3 php8.3-cli php8.3-mysql php8.3-gd php8.3-xml \
      php8.3-curl php8.3-mbstring php8.3-intl php8.3-zip php8.3-soap php8.3-bcmath \
      php8.3-opcache mariadb-server mariadb-client unzip \
 && a2enmod ssl rewrite headers expires \
 && a2dissite 000-default \
 && printf 'Listen 127.0.0.1:443\n' > /etc/apache2/ports.conf \
 && printf 'ServerName localhost\n' > /etc/apache2/conf-enabled/cua-name.conf \
 && printf 'max_input_vars=5000\nmemory_limit=512M\nupload_max_filesize=64M\npost_max_size=65M\nmax_execution_time=120\n' \
      > /etc/php/8.3/mods-available/cua-native.ini \
 && phpenmod cua-native \
 && rm -rf /var/lib/apt/lists/*
