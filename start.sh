#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting Gunicorn on port ${PORT:-3000}..."
gunicorn cna_inadimplentes.wsgi:application --bind 0.0.0.0:${PORT:-3000} --workers 2
