# Neutranscriber Server

A REST API service that converts piano audio recordings into MIDI files using advanced machine learning models.

## What it does

- **Audio to MIDI conversion**: Upload audio files containing piano music and get back MIDI files
- **Asynchronous processing**: Long transcription jobs run in the background without blocking
- **Multiple audio formats**: Supports MP3, WAV, FLAC, OGG, M4A, AIFF, AAC
- **REST API**: Simple HTTP endpoints for integration with web apps or scripts

## Quick Start

### Prerequisites

- Python 3.8+
- Redis server
- macOS, Linux, or Windows

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd neutranscriber-server
   ```

2. **Set up Python virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Service

You need to start three components:

1. **Start Redis server** (in terminal 1):
   ```bash
   redis-server
   ```

2. **Start Celery worker** (in terminal 2):
   ```bash
   celery -A celery_worker.celery worker --loglevel=info
   ```
   
   Note: For local development, make sure `celery_worker.py` uses `redis://localhost:6379/0` instead of `redis://redis:6379/0`

3. **Start Flask API server** (in terminal 3):
   ```bash
   python app.py
   ```

The API will be available at `http://localhost:9000`

### Using Docker (Alternative)

If you have Docker installed:

```bash
docker-compose up --build
```

This starts all services automatically.

## Quick Test

1. **Check if the service is running**:
   ```bash
   curl http://localhost:9000/api/health
   ```

2. **Upload a piano audio file**:
   ```bash
   curl -X POST -F "file=@your_piano_recording.mp3" http://localhost:9000/api/transcribe
   ```

3. **Check transcription status** (use the task_id from step 2):
   ```bash
   curl http://localhost:9000/api/transcription_status/YOUR_TASK_ID
   ```

4. **Download the MIDI file** (when complete):
   ```bash
   curl -O http://localhost:9000/api/download_midi/YOUR_MIDI_FILENAME.mid
   ```

## API Documentation

For complete API documentation with examples in Python, JavaScript, and cURL, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

## File Structure

```
neutranscriber-server/
├── app.py                 # Flask web server
├── celery_worker.py       # Background task worker
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Multi-service Docker setup
├── static/
│   ├── audio/            # Uploaded audio files
│   └── midi/             # Generated MIDI files
└── model/                # ML model cache (auto-created)
```

## Architecture

- **Flask**: Web server providing REST API endpoints
- **Celery**: Asynchronous task queue for background processing
- **Redis**: Message broker and result backend for Celery
- **piano_transcription_inference**: ML library for piano transcription

## Supported Audio Formats

- MP3 (.mp3)
- WAV (.wav) 
- FLAC (.flac)
- OGG (.ogg)
- M4A (.m4a)
- AIFF (.aiff)
- AAC (.aac)

## Troubleshooting

### Common Issues

1. **"Connection refused" error**: Make sure Redis is running
2. **"No workers available" error**: Make sure Celery worker is running
3. **"File not found" error**: Check that audio file paths are correct
4. **Long processing times**: Normal for longer audio files (1-5x real-time)

### Logs

- Flask server logs appear in the terminal where you ran `python app.py`
- Celery worker logs appear in the terminal where you ran the worker command
- Redis logs appear in the Redis server terminal

## Development

### Making Changes

1. **For API changes**: Edit `app.py`
2. **For transcription logic**: Edit `celery_worker.py`
3. **For dependencies**: Update `requirements.txt`

### Configuration

- **Upload folder**: `static/audio/` (configurable in `app.py`)
- **MIDI output folder**: `static/midi/` (configurable in both files)
- **Server port**: 9000 (configurable in `app.py`)
- **Redis URL**: Configure in `celery_worker.py`

## Production Deployment

For production use:

1. Use a proper WSGI server like Gunicorn instead of Flask's development server
2. Set up Redis with persistence and security
3. Configure proper logging and monitoring
4. Set up reverse proxy (nginx) for SSL and load balancing
5. Consider using Docker for consistent deployments

Example production start:
```bash
gunicorn --bind 0.0.0.0:9000 app:app
```