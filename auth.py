"""
Authentication routes for Google OAuth and JWT token management
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from google.auth.transport import requests
from google.oauth2 import id_token
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport.requests import Request as GoogleRequest
import requests as http_requests
import os
from datetime import timedelta
from models import db, User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/google/callback', methods=['POST'])
def google_callback():
    """
    Handle Google OAuth callback
    Expects: { "code": "<authorization_code>" }

    The authorization code is exchanged for ID token on the backend
    Returns: { "access_token": "<jwt_token>", "user": {...} }
    """
    try:
        data = request.get_json()
        code = data.get('code')

        if not code:
            return jsonify({'error': 'Missing authorization code'}), 400

        # Exchange code for token using Google's token endpoint
        token_url = 'https://oauth2.googleapis.com/token'

        token_data = {
            'code': code,
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'redirect_uri': 'postmessage',  # postmessage for implicit/auth-code redirect
            'grant_type': 'authorization_code',
        }

        try:
            token_response = http_requests.post(token_url, data=token_data)
            token_response.raise_for_status()
            token_json = token_response.json()
        except http_requests.RequestException as e:
            print(f"Error exchanging code for token: {e}")
            return jsonify({'error': 'Failed to exchange authorization code'}), 401

        # Get ID token from response
        id_token_str = token_json.get('id_token')
        if not id_token_str:
            return jsonify({'error': 'No ID token in response'}), 401

        # Verify the ID token with Google
        idinfo = verify_oauth2_token(
            id_token_str,
            GoogleRequest(),
            os.getenv('GOOGLE_CLIENT_ID')
        )

        # Extract user information from token
        email = idinfo.get('email')
        google_id = idinfo.get('sub')
        name = idinfo.get('name')
        picture = idinfo.get('picture')

        if not email or not google_id:
            return jsonify({'error': 'Invalid token'}), 400

        # Find or create user
        user = User.query.filter_by(email=email).first()

        if user:
            # Update last login
            user.last_login = db.func.now()
            db.session.commit()
        else:
            # Create new user
            user = User(
                email=email,
                google_id=google_id,
                name=name,
                picture_url=picture
            )
            db.session.add(user)
            db.session.commit()

        # Generate JWT tokens
        # Note: identity must be a string for Flask-JWT-Extended
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(hours=24)
        )
        refresh_token = create_refresh_token(identity=str(user.id))

        return jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict()
        }), 200

    except ValueError as e:
        # Invalid token
        print(f"Token verification error: {e}")
        return jsonify({'error': 'Invalid token', 'message': str(e)}), 401
    except Exception as e:
        print(f"Authentication error: {e}")
        return jsonify({'error': 'Authentication failed', 'message': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    Logout endpoint - frontend should discard tokens
    In production, you might add token blacklisting here
    """
    return jsonify({'message': 'Logged out successfully'}), 200


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token using refresh token
    Requires: Authorization header with refresh token (Bearer <refresh_token>)
    Returns: { "access_token": "<new_jwt_token>" }
    """
    from flask_jwt_extended import get_jwt_identity

    user_id = get_jwt_identity()
    access_token = create_access_token(
        identity=user_id,
        expires_delta=timedelta(hours=24)
    )
    return jsonify({'access_token': access_token}), 200
