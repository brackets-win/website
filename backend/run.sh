#!/bin/bash

python3 manage.py migrate

gunicorn --bind :8000 --workers 2 website.wsgi
