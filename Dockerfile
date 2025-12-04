FROM python:3.14.1-slim
WORKDIR /app
COPY ./src .
RUN pip install -r requirements.txt

CMD ["python", "app.py"]
