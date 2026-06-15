release: python manage.py migrate --noinput && python manage.py createcachetable
web: gunicorn compass.wsgi --bind 0.0.0.0:$PORT --log-file -
