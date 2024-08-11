FROM python

COPY requirements.txt /requirements.txt
RUN pip install -r requirements.txt \
    && mkdir /app \
    && mkdir /hashdir \
    && useradd rssfeed \
    && chown -R rssfeed /hashdir

ENV PYTHONUNBUFFERED 1
ENV HASH_DIR /hashdir/
ENV FEEDS_FILE /app/feeds.json
    
USER rssfeed

COPY app /app/
COPY feeds.json /app/

CMD /app/main.py
