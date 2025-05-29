from celery import Celery
import os
import time
import traceback
from piano_transcription_inference import PianoTranscription, sample_rate, load_audio

# Configure Celery
celery = Celery(
    'tasks',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0'
)

# Define the directory for storing MIDI files
STORE_FOLDER = 'static/midi/'
if not os.path.exists(STORE_FOLDER):
    os.makedirs(STORE_FOLDER)


@celery.task
def transcribe_audio_task(audio_path):
    """
    This is the Celery task that will run the piano transcription in the background.
    """
    try:
        print(f"Starting transcription for: {audio_path}")

        # Check if file exists
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Define the output path for the MIDI file
        filename = os.path.basename(audio_path)
        output_midi_path = os.path.join(
            os.getcwd(), STORE_FOLDER, filename.replace('.mp3', '.mid'))

        print(f"Output MIDI path: {output_midi_path}")

        # Load audio
        print("Loading audio...")
        (audio, _) = load_audio(audio_path, sr=sample_rate, mono=True)
        print(f"Audio loaded successfully, shape: {audio.shape}")

        # Transcriptor
        print("Initializing transcriptor...")
        transcriptor = PianoTranscription(device='cpu', checkpoint_path=None)

        # Transcribe and write out to MIDI file
        print("Starting transcription...")
        start_time = time.time()
        transcriptor.transcribe(audio, output_midi_path)
        transcription_time = time.time() - start_time

        print(f"Transcription completed in {transcription_time} seconds")

        return {
            'status': 'SUCCESS',
            'midi_filename': os.path.basename(output_midi_path),
            'transcription_time': round(transcription_time, 2)
        }
    except Exception as e:
        error_msg = f"Error in transcription: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {'status': 'FAILURE', 'error': error_msg}
