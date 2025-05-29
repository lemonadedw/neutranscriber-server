import os
import time
from piano_transcription_inference import PianoTranscription, sample_rate, load_audio


filename = os.path.basename('./a.mp3')
output_midi_path = os.path.join(
    os.getcwd(), 'static/midi', filename.replace('.mp3', '.mid'))
# Ensure the output directory exists

# Load audio
(audio, _) = load_audio(filename, sr=sample_rate, mono=True)

# Transcriptor
transcriptor = PianoTranscription(device='cpu', checkpoint_path=None)

# Transcribe and write out to MIDI file
start_time = time.time()
transcriptor.transcribe(audio, output_midi_path)
transcription_time = time.time() - start_time
print("status: SUCCESS")
print(f"midi_filename: {os.path.basename(output_midi_path)}")
