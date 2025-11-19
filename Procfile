# Dual-process deployment for Railway/Heroku
bot: python bot.py
web: gunicorn --bind 0.0.0.0:$PORT --worker-class gevent --workers 1 --timeout 120 --preload backend:app
