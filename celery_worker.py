from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded, MaxRetriesExceededError
import os
import time
import traceback
import json
import redis
from piano_transcription_inference import PianoTranscription, sample_rate, load_audio

celery = Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Celery configuration for failure handling
celery.conf.update(
    task_reject_on_worker_lost=True,      # Reject tasks if worker dies unexpectedly
    broker_connection_retry_on_startup=True,
    task_acks_late=True,                  # Only acknowledge after task completes
    worker_prefetch_multiplier=1,         # Grab one task at a time (fairer)
    task_track_started=True,              # Track when task actually starts
)

# Redis clients for different purposes
redis_dlq = redis.Redis(host='localhost', port=6379, db=2)  # Dead-letter queue

STORE_FOLDER = 'static/midi/'
if not os.path.exists(STORE_FOLDER):
    os.makedirs(STORE_FOLDER)


def _store_in_dlq(task_id, error_msg):
    """
    Store failed task in dead-letter queue (DLQ) for monitoring and manual replay.

    Allows you to:
    - Monitor which tasks are failing
    - Replay failed tasks manually
    - Analyze failure patterns
    - Alert on critical failures
    """
    try:
        failed_task_data = {
            'task_id': task_id,
            'error': error_msg,
            'timestamp': time.time(),
            'status': 'DEAD_LETTER'
        }
        # Store in Redis DB 2 (separate from Celery broker)
        redis_dlq.hset('dlq:tasks', task_id, json.dumps(failed_task_data))
        # Keep list of all failed tasks
        redis_dlq.lpush('dlq:task_ids', task_id)
        print(f"📛 Failed task {task_id} stored in DLQ")
    except Exception as e:
        print(f"Failed to store task {task_id} in DLQ: {e}")


def emit_progress(task_id, state, data):
    """
    Emit progress updates via WebSocket using Flask-SocketIO with Redis message queue.

    When using message_queue with multiple Gunicorn workers:
    - SocketIO(message_queue='...') creates a connection to Redis
    - emit() publishes the event to Redis with room filtering
    - Redis broadcasts to all workers, each worker filters for the room
    - Clients in the specific room (task_id) receive the event
    - No need for broadcast=True here - that's handled by the message queue

    SECURITY: The 'to' parameter ensures only clients in this task's room receive updates.
    This prevents information leakage between different users' transcription tasks.
    """
    try:
        from flask_socketio import SocketIO

        # Create a SocketIO client connected to the Redis message queue
        socketio = SocketIO(message_queue='redis://localhost:6379/1')

        # Emit to the message queue - Redis will handle distribution to the specific room
        # The 'to' parameter restricts the event to clients in this task_id room
        socketio.emit('transcription_update', {
            'task_id': task_id,
            'state': state,
            'data': data
        }, to=task_id)  # ← Only clients in this room receive the event
    except Exception as e:
        print(f"Failed to emit progress: {e}")
        traceback.print_exc()


def _handle_task_failure(task_id, state, error_msg, retries=None):
    """
    Centralized handler for task failures.
    Emits progress update and stores in dead-letter queue.
    """
    data = {
        'status': 'FAILURE',
        'error': error_msg,
    }
    if retries is not None:
        data['retry_attempt'] = retries

    emit_progress(task_id, state, data)
    _store_in_dlq(task_id, error_msg)


@celery.task(
    bind=True,
    autoretry_for=(Exception,),              # Retry on any exception
    retry_kwargs={'max_retries': 3},         # Max 3 retries
    retry_backoff=True,                      # Exponential backoff
    retry_backoff_max=600,                   # Max 10 min between retries
    retry_jitter=True,                       # Prevent thundering herd
    time_limit=3600,                         # Hard kill after 1 hour
    soft_time_limit=3300                     # Soft warning at 55 min
)
def transcribe_audio_task(self, audio_path):
    """
    This is the Celery task that will run the piano transcription in the background.
    """
    task_id = self.request.id

    try:
        emit_progress(task_id, 'PROCESSING', {
                      'status': 'Starting transcription...'})

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Define the output path for the MIDI file
        filename = os.path.basename(audio_path)
        filename_without_ext = os.path.splitext(filename)[0]
        output_midi_path = os.path.join(
            os.getcwd(), STORE_FOLDER, f"{filename_without_ext}.mid")

        emit_progress(task_id, 'PROCESSING', {'status': 'Loading audio...'})
        (audio, _) = load_audio(audio_path, sr=sample_rate, mono=True)

        emit_progress(task_id, 'PROCESSING', {
                      'status': 'Initializing transcriber...'})
        transcriber = PianoTranscription(device='cpu', checkpoint_path=None)

        # Transcribe and write out to MIDI file
        emit_progress(task_id, 'PROCESSING', {
                      'status': 'Transcribing audio...'})
        start_time = time.time()
        transcriber.transcribe(audio, output_midi_path)
        transcription_time = time.time() - start_time

        result = {
            'status': 'SUCCESS',
            'midi_filename': os.path.basename(output_midi_path),
            'transcription_time': round(transcription_time, 2)
        }
        emit_progress(task_id, 'SUCCESS', result)
        return result

    except SoftTimeLimitExceeded:
        # Task is taking too long (> 55 min). Gracefully handle before hard kill
        error_msg = "Transcription timed out (exceeded 55 minutes)"
        print(
            f"⏱️  Task {task_id} approaching timeout limit, cleaning up gracefully...")
        _handle_task_failure(task_id, 'FAILURE', error_msg)
        raise

    except MaxRetriesExceededError:
        # Task failed 3 times and is giving up
        error_msg = "Transcription failed after 3 retry attempts"
        print(f"❌ Task {task_id} exceeded max retries: {error_msg}")
        _handle_task_failure(task_id, 'FAILURE', error_msg)
        return {'status': 'FAILURE', 'error': error_msg}

    except Exception as e:
        error_msg = f"Error in transcription: {str(e)}"
        print(f"⚠️  Task {task_id} failed (will retry): {error_msg}")
        traceback.print_exc()
        _handle_task_failure(task_id, 'FAILURE', error_msg,
                             retries=self.request.retries)
        # This triggers the retry logic defined in @celery.task decorator
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
