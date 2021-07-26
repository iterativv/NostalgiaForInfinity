FROM freqtradeorg/freqtrade:develop

COPY --chown=1000:1000  tests/requirements.txt /freqtrade

RUN pip install --user --no-cache-dir --no-build-isolation -r /freqtrade/requirements.txt
