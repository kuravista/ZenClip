import os
import sys
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))
sys.path.insert(0, os.path.join(BASE_DIR, 'src', 'services', 'media'))

# Recovery launcher should not force sidecar mode; callers can still set CLIP_SIDECAR_DIR explicitly.
os.environ.setdefault('CLIP_RECOVERY_SAFE', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
os.environ.setdefault('PYTHONUNBUFFERED', '1')

from src.app import app

if __name__ == '__main__':
    port = int(os.environ.get('CLIP_BACKEND_PORT', '9479'))
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    for handler in log_config.get('handlers', {}).values():
        handler['stream'] = 'ext://sys.stdout'
    uvicorn.run(app, host='127.0.0.1', port=port, workers=1, log_level='warning', log_config=log_config)
