FROM python:3.15.0b3-slim
WORKDIR /app
COPY ./src .
RUN pip install -r requirements.txt

CMD ["python", "app.py"]
