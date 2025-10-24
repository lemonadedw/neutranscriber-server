from celery import Celery
import os
import time
import traceback
from piano_transcription_inference import PianoTranscription, sample_rate, load_audio

celery = Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# The directory for storing MIDI files
STORE_FOLDER = 'static/midi/'
if not os.path.exists(STORE_FOLDER):
    os.makedirs(STORE_FOLDER)


def emit_progress(task_id, state, data):
    """
    Emit progress updates via WebSocket using Flask-SocketIO with Redis message queue.

    When using message_queue with multiple Gunicorn workers:
    - SocketIO(message_queue='...') creates a connection to Redis
    - emit() publishes the event to Redis
    - Redis broadcasts to ONE worker, which then emits to the client
    - No need for broadcast=True here - that's handled by the message queue
    """
    try:
        from flask_socketio import SocketIO

        # Create a SocketIO client connected to the Redis message queue
        socketio = SocketIO(message_queue='redis://localhost:6379/1')

        # Emit to the message queue - Redis will handle distribution to clients
        socketio.emit('transcription_update', {
            'task_id': task_id,
            'state': state,
            'data': data
        })
    except Exception as e:
        print(f"Failed to emit progress: {e}")
        traceback.print_exc()


@celery.task(bind=True)
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

    except Exception as e:
        error_msg = f"Error in transcription: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        error_result = {'status': 'FAILURE', 'error': error_msg}
        emit_progress(task_id, 'FAILURE', error_result)
        return error_result
