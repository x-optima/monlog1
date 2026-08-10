# Образ Chronograf. CHRONOGRAF_TAG задаётся в .env-latest
ARG CHRONOGRAF_TAG
FROM chronograf:$CHRONOGRAF_TAG

# Источник данных InfluxDB для sandbox
ADD ./sandbox.src ./usr/share/chronograf/resources/
# Пример ресурса Kapacitor
ADD ./sandbox-kapa.kap ./usr/share/chronograf/resources/
