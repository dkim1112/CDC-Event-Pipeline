"""
Analytics DB connection helper.
"""

import psycopg2
from consumer.config import ANALYTICS_DB


def get_connection():
    return psycopg2.connect(**ANALYTICS_DB)
