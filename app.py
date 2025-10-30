# Monkey patch for eventlet (must be ABSOLUTELY first!)
import os
import uuid
import time
from datetime import datetime
from auth import auth_bp
from models import db, User, Transcription
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from celery.result import AsyncResult
from celery_worker import transcribe_audio_task
import requests
import eventlet
eventlet.monkey_patch()

# Now safe to import everything else

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Content-Type", "Authorization"],
    "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"]
}})

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://henrywang@localhost:5432/neutranscriber_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# JWT configuration
app.config['JWT_SECRET_KEY'] = os.getenv(
    'JWT_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 86400  # 24 hours

# Initialize extensions
db.init_app(app)
jwt = JWTManager(app)

# Initialize database tables on app startup (needed for gunicorn)
# db.create_all() is idempotent - it only creates tables that don't exist
with app.app_context():
    db.create_all()

# JWT error handlers


@jwt.unauthorized_loader
def unauthorized_callback(callback):
    print(f"=== JWT UNAUTHORIZED ERROR: {callback} ===")
    return jsonify({'error': 'Missing or invalid Authorization header', 'details': str(callback)}), 401


@jwt.invalid_token_loader
def invalid_token_callback(callback):
    print(f"=== JWT INVALID TOKEN ERROR: {callback} ===")
    return jsonify({'error': 'Invalid JWT token', 'details': str(callback)}), 422


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    print(f"=== JWT EXPIRED TOKEN ERROR ===")
    return jsonify({'error': 'Token has expired'}), 401


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

# Register authentication blueprint
app.register_blueprint(auth_bp)

app.config['UPLOAD_FOLDER'] = 'static/audio/'
app.config['STORE_FOLDER'] = 'static/midi/'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aiff', 'aac'}

# Ensure the upload and storage directories exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['STORE_FOLDER']):
    os.makedirs(app.config['STORE_FOLDER'])


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_id_from_jwt():
    """
    Extract and convert user_id from JWT token.
    get_jwt_identity() returns a string, this converts it to int.
    Used by all protected endpoints.
    """
    return int(get_jwt_identity())


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/transcribe', methods=['POST'])
@jwt_required()
def upload_and_transcribe():
    """
    API endpoint to upload an audio file and start the transcription process.
    Requires: JWT authentication token
    """
    print("=== Transcribe endpoint called ===")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request files: {request.files}")
    print(f"Request form: {request.form}")

    user_id = get_user_id_from_jwt()
    print(f"User ID from JWT: {user_id}")

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Create database record for transcription
        transcription = Transcription(
            user_id=user_id,
            filename=filename,
            original_filename=file.filename,
            status='PENDING'
        )
        db.session.add(transcription)
        db.session.commit()

        # background transcription task by Celery
        # Note: Only pass filepath, task uses self.request.id as task_id
        task = transcribe_audio_task.delay(filepath)

        # Return the task ID and transcription info to the client
        return jsonify({
            'task_id': task.id,
            'transcription_id': transcription.id,
            'status': 'processing'
        }), 202
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
@jwt_required()
def download_midi(filename):
    """
    API endpoint to download the generated MIDI file.
    Requires: JWT authentication token
    Security: Verifies user owns the transcription before download
    """
    user_id = get_user_id_from_jwt()

    # Verify user owns this MIDI file by checking the transcription record
    transcription = Transcription.query.filter_by(
        user_id=user_id,
        midi_filename=filename
    ).first()

    if not transcription:
        return jsonify({'error': 'File not found or access denied'}), 404

    midi_path = os.path.join(app.config['STORE_FOLDER'], filename)
    if os.path.exists(midi_path):
        return send_from_directory(app.config['STORE_FOLDER'], filename, as_attachment=True)
    else:
        return jsonify({'error': 'File not found on disk'}), 404


@app.route('/api/user/transcriptions', methods=['OPTIONS'])
def transcriptions_options():
    """
    Handle CORS preflight requests for /api/user/transcriptions
    """
    return '', 204


@app.route('/api/user/transcriptions', methods=['GET'])
@jwt_required()
def get_user_transcriptions():
    """
    API endpoint to retrieve all transcriptions for the authenticated user.
    Returns transcriptions sorted by newest first.
    Requires: JWT authentication token
    """
    user_id = get_user_id_from_jwt()

    transcriptions = Transcription.query.filter_by(
        user_id=user_id
    ).order_by(Transcription.created_at.desc()).all()

    return jsonify({
        'transcriptions': [t.to_dict() for t in transcriptions]
    }), 200


@app.route('/api/user/transcriptions', methods=['POST'])
@jwt_required()
def save_user_transcription():
    """
    API endpoint to save or update a transcription for the authenticated user.

    Requires: JWT authentication token
    Body: {
        transcription_id?,      # If present: UPDATE existing record
        midi_filename,
        processing_time,
        status,
        original_filename?
    }

    Two modes:
    - If transcription_id provided: UPDATE the record (from Celery task completion)
    - If transcription_id missing: CREATE new record
    """
    user_id = get_user_id_from_jwt()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        transcription_id = data.get('transcription_id')

        if transcription_id:
            return _update_transcription(user_id, transcription_id, data)
        else:
            return _create_transcription(user_id, data)

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error saving transcription: {e}")
        return jsonify({'error': 'Failed to save transcription', 'details': str(e)}), 500


def _update_transcription(user_id, transcription_id, data):
    """Update existing transcription record with final results."""
    transcription = Transcription.query.filter_by(
        id=transcription_id,
        user_id=user_id
    ).first()

    if not transcription:
        return jsonify({'error': 'Transcription not found'}), 404

    # Update fields
    transcription.midi_filename = data.get('midi_filename')
    transcription.status = data.get('status', 'SUCCESS')
    transcription.processing_time = data.get('processing_time')
    transcription.completed_at = datetime.utcnow()

    db.session.commit()
    print(
        f"✅ Updated transcription {transcription_id} for user {user_id}: {transcription.midi_filename}")

    return jsonify({
        'message': 'Transcription updated',
        'transcription': transcription.to_dict()
    }), 201


def _create_transcription(user_id, data):
    """Create new transcription record."""
    transcription = Transcription(
        user_id=user_id,
        filename=data.get('filename', 'unknown'),
        original_filename=data.get('original_filename', 'unknown'),
        midi_filename=data.get('midi_filename'),
        status=data.get('status', 'PENDING'),
        processing_time=data.get('processing_time', 0),
        created_at=datetime.utcnow()
    )

    db.session.add(transcription)
    db.session.commit()
    print(
        f"✅ Saved transcription for user {user_id}: {transcription.midi_filename}")

    return jsonify({
        'message': 'Transcription saved',
        'transcription': transcription.to_dict()
    }), 201


@app.route('/api/user/transcriptions/<int:transcription_id>', methods=['DELETE'])
@jwt_required()
def delete_user_transcription(transcription_id):
    """
    API endpoint to delete a specific transcription for the authenticated user.
    Requires: JWT authentication token
    Parameter: transcription_id (integer)
    """
    user_id = get_user_id_from_jwt()

    try:
        # Find the transcription and verify it belongs to the user
        transcription = Transcription.query.filter_by(
            id=transcription_id,
            user_id=user_id
        ).first()

        if not transcription:
            return jsonify({'error': 'Transcription not found'}), 404

        db.session.delete(transcription)
        db.session.commit()

        print(
            f"🗑️  Deleted transcription {transcription_id} for user {user_id}")

        return jsonify({
            'message': 'Transcription deleted',
            'id': transcription_id
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting transcription: {e}")
        return jsonify({'error': 'Failed to delete transcription', 'details': str(e)}), 500


@app.route('/api/user/transcriptions', methods=['DELETE'])
@jwt_required()
def delete_all_user_transcriptions():
    """
    API endpoint to delete all transcriptions for the authenticated user.
    CAUTION: This is for cleanup purposes only. Use with care.
    Requires: JWT authentication token
    """
    user_id = get_user_id_from_jwt()

    try:
        # Delete all transcriptions for this user
        deleted_count = Transcription.query.filter_by(user_id=user_id).delete()
        db.session.commit()

        print(f"🗑️  Deleted {deleted_count} transcriptions for user {user_id}")

        return jsonify({
            'message': f'Deleted {deleted_count} transcriptions',
            'deleted_count': deleted_count
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting transcriptions: {e}")
        return jsonify({'error': 'Failed to delete transcriptions', 'details': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Simple health check endpoint.
    """
    return jsonify({'status': 'ok'}), 200


@app.route('/api/auth/user/profile-picture', methods=['GET'])
@jwt_required()
def get_profile_picture():
    """
    Proxy endpoint to get user's profile picture
    Avoids CORS issues with Google's CDN by proxying through backend
    Requires: JWT authentication token
    Returns: Profile picture image file
    """
    user_id = get_user_id_from_jwt()

    # Get user from database
    user = User.query.get(user_id)
    if not user or not user.picture_url:
        return jsonify({'error': 'Profile picture not found'}), 404

    try:
        # Fetch the image from Google's CDN
        response = requests.get(user.picture_url, timeout=5)
        response.raise_for_status()

        # Return the image with appropriate headers
        # Use must-revalidate to check cache on each request when user changes
        return response.content, 200, {
            'Content-Type': response.headers.get('Content-Type', 'image/jpeg'),
            'Cache-Control': 'private, max-age=0, must-revalidate',
            'ETag': f'"{user_id}"'  # ETag based on user ID
        }
    except Exception as e:
        print(f"Error fetching profile picture: {e}")
        return jsonify({'error': 'Failed to fetch profile picture'}), 500


@socketio.on('connect')
def handle_connect():
    """
    Handle WebSocket connection.
    """
    emit('test_connection', {'message': 'WebSocket connected successfully'})


@socketio.on('join_task')
def on_join_task(data):
    """
    Handle client joining a task-specific room.
    Client calls this with: socket.emit('join_task', {'task_id': task_id})
    This ensures the client only receives updates for their specific task.
    """
    task_id = data.get('task_id')
    if task_id:
        join_room(task_id)
        emit('message', {
            'status': 'joined',
            'task_id': task_id,
            'message': f'Joined room for task {task_id}'
        })


@socketio.on('leave_task')
def on_leave_task(data):
    """
    Handle client leaving a task-specific room.
    Client calls this with: socket.emit('leave_task', {'task_id': task_id})
    """
    task_id = data.get('task_id')
    if task_id:
        leave_room(task_id)
        emit('message', {
            'status': 'left',
            'task_id': task_id,
            'message': f'Left room for task {task_id}'
        })


@socketio.on('disconnect')
def handle_disconnect():
    """
    Handle WebSocket disconnection.
    """
    pass


if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create database tables
    socketio.run(app, debug=True, host='0.0.0.0',
                 port=9000, allow_unsafe_werkzeug=True)
