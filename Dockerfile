from python:3.12.2

WORKDIR /app/

RUN poetry install

RUN /main.py