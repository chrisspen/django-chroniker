#!/bin/bash
set -e
if [ ! -d .env ]; then
    virtualenv -p python3.7 .env
    . .env/bin/activate
    pip install -U pip setuptools wheel
    pip install -r requirements-test.txt
fi
. .env/bin/activate
python setup.py sdist
twine upload dist/*
