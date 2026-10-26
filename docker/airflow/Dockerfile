FROM apache/airflow:3.3.2-python3.12
# The pipeline package needs these on top of what Airflow ships with.
RUN pip install --no-cache-dir boto3 "psycopg[binary]" pypdf pyyaml fastembed neo4j
RUN mkdir -p /opt/airflow/fastembed_cache
