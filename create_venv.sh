#!/bin/sh

if ! [ -x "$(command -v pyenv)" ]; then
  echo 'Error: pyenv is not installed.' >&2
  exit 1
fi

PROJECT_DIR=$(pwd)
rm -rf $PROJECT_DIR/.venv

poetry config virtualenvs.in-project true
poetry install