import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from celery.result import AsyncResult
from celery_worker import transcribe_audio_task

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config['UPLOAD_FOLDER'] = 'static/audio/'
app.config['STORE_FOLDER'] = 'static/midi/'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aiff', 'aac'}

# Ensure the upload and storage directories exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['STORE_FOLDER']):
    os.makedirs(app.config['STORE_FOLDER'])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/transcribe', methods=['POST'])
def upload_and_transcribe():
    """
    API endpoint to upload an audio file and start the transcription process.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Start the background task
        task = transcribe_audio_task.delay(filepath)

        # Return the task ID to the client
        return jsonify({'task_id': task.id}), 202
    else:
        return jsonify({'error': 'File type not allowed'}), 400


@app.route('/api/transcription_status/<task_id>', methods=['GET'])
def get_transcription_status(task_id):
    """
    API endpoint for the client to poll for the transcription status.
    """
    task_result = AsyncResult(task_id)
    if task_result.state == 'PENDING':
        response = {
            'state': task_result.state,
            'status': 'Pending...'
        }
    elif task_result.state != 'FAILURE':
        response = {
            'state': task_result.state,
            'result': task_result.info,
        }
    else:
        # Something went wrong in the background job
        response = {
            'state': task_result.state,
            'status': str(task_result.info),  # this is the exception raised
        }
    return jsonify(response)


@app.route('/api/download_midi/<filename>', methods=['GET'])
def download_midi(filename):
    """
    API endpoint to download the generated MIDI file.
    """
    midi_path = os.path.join(app.config['STORE_FOLDER'], filename)
    if os.path.exists(midi_path):
        from flask import send_from_directory
        return send_from_directory(app.config['STORE_FOLDER'], filename, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Simple health check endpoint.
    """
    return jsonify({'status': 'ok'}), 200


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=9000)
