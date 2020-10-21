#!/bin/bash

git submodule update --init

rm -rf .venv
python3.7 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r lilu/requirements.txt
pip install -r requirements.txt