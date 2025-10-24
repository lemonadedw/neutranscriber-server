#!/bin/bash
# Run Flask-SocketIO server for production with multi-worker support

# Production with 4 workers (supports 50+ concurrent users)
# Client-side de-duplication handles multiple worker broadcasts
gunicorn --worker-class eventlet -w 4 --bind 0.0.0.0:9000 app:app

# For development (single worker with auto-reload), uncomment line below:
# gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:9000 --reload app:app

# Note: Adjust worker count based on your CPU cores
# Rule of thumb: (2 x CPU cores) + 1
# e.g., 4 cores = 9 workers max recommended
