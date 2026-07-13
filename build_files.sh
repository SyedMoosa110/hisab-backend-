#!/bin/bash
python3 -m venv build_env
source build_env/bin/activate
pip install -r requirements.txt
python manage.py collectstatic --noinput --clear
mkdir -p staticfiles_build/static
cp -r staticfiles/. staticfiles_build/static/
