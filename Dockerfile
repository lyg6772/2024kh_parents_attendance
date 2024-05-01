FROM python:3.12.2

RUN apt-get update && apt-get upgrade -y \
    && apt install -y sudo nginx unzip less \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i 's/CipherString = DEFAULT@SECLEVEL=2/CipherString = DEFAULT@SECLEVEL=1/g' /etc/ssl/openssl.cnf \
    && pip3 install poetry

RUN mkdir /app/

WORKDIR /app

COPY . .

RUN poetry install

CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
