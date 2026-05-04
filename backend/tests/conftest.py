import sys
import os

# Add backend/src to sys.path so imports like "from services.automation..." work
src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
