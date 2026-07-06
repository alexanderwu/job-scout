"""Cron config module for ``rq cron`` — run as:

    rq cron jobscout.schedules --url $REDIS_URL

RQ imports this module and executes it top to bottom; each
``cron.register`` call here becomes a periodically-enqueued job. Kept
separate from worker.py so "what runs on a schedule" is one obvious,
declarative file.
"""

from jobscout.worker import register_cron

register_cron()
