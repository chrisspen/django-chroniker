#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "[$(date)] Removing existing virtualenv if it exists."
[ -d .env ] && rm -Rf .env

echo "[$(date)] Creating virtual environment."
python3.8 -m venv .env

echo "[$(date)] Activating virtual environment."
. .env/bin/activate

echo "[$(date)] Upgrading pip."
pip install -U pip

echo "[$(date)] Installing pip requirements."
pip install -r requirements.txt -r requirements-test.txt
