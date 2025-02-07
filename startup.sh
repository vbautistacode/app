#!/bin/bash

# Instala drivers ODBC para SQL Server
apt-get update
apt-get install -y msodbcsql17 unixodbc-dev 

# Inicia a aplicação
gunicorn --bind=0.0.0.0 --timeout 600 app:app

chmod +x startup.sh