# Shared state for processing jobs
# In a production app, this should be a database (Redis/Postgres)
import threading
jobs = {}
jobs_lock = threading.RLock()

