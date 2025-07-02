FROM python:3.9
WORKDIR /app
COPY requirements.txt .
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
<<<<<<< HEAD
CMD ["python", "monefy_bot/monefy_bot.py"]
=======
CMD ["python", "monefy_bot/monefy_bot.py"]
>>>>>>> 804c6ac44303ddc1190f3d106d7aefbebb0862f6
