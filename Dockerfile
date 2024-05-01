from python:3.12.2

WORKDIR /

RUN poetry install

RUN /run.py