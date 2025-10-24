# Monkey patch for eventlet (must be ABSOLUTELY first!)
from celery_worker import transcribe_audio_task
from celery.result import AsyncResult
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from flask import Flask, request, jsonify
import os
import eventlet
eventlet.monkey_patch()

# Now safe to import everything else


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Use Redis as message queue for multi-worker WebSocket support
# This allows multiple Gunicorn workers to share WebSocket connections
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    message_queue='redis://localhost:6379/1',  # Use Redis db 1 for message queue
    logger=False,
    engineio_logger=False
)

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
        import uuid
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # background transcription task by Celery
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
    if not task_id or not isinstance(task_id, str):
        return jsonify({'error': 'Invalid task ID'}), 400

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
        # FAILURE
        response = {
            'state': task_result.state,
            'status': str(task_result.info),  # the exception raised
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


@socketio.on('connect')
def handle_connect():
    """
    Handle WebSocket connection.
    """
    emit('test_connection', {'message': 'WebSocket connected successfully'})


@socketio.on('disconnect')
def handle_disconnect():
    """
    Handle WebSocket disconnection.
    """
    pass


if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0',
                 port=9000, allow_unsafe_werkzeug=True)
