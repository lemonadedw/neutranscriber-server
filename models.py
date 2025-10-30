"""
Database models for NeuTranscriber using SQLAlchemy
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    """User model for storing Google OAuth authenticated users"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120))
    picture_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to transcriptions
    transcriptions = db.relationship(
        'Transcription', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.email}>'

    def to_dict(self):
        """Convert user to dictionary for JSON response"""
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'picture': self.picture_url,
            'created_at': self.created_at.isoformat(),
        }


class Transcription(db.Model):
    """Transcription model for storing user transcription history"""
    __tablename__ = 'transcriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id'), nullable=False, index=True)

    # File information
    # UUID_original_name.mp3
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))  # User's original filename
    midi_filename = db.Column(db.String(255))  # UUID.mid

    # Status and results
    # PENDING, PROCESSING, SUCCESS, FAILURE
    status = db.Column(db.String(50), default='PENDING')
    error_message = db.Column(db.String(500))
    processing_time = db.Column(db.Float)  # seconds

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Transcription {self.id} - {self.filename}>'

    def to_dict(self):
        """Convert transcription to dictionary for JSON response"""
        return {
            'id': self.id,
            'filename': self.original_filename or self.filename,
            'midi_filename': self.midi_filename,
            'status': self.status,
            'error_message': self.error_message,
            'processing_time': self.processing_time,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
