# Google OAuth Authentication Setup Guide

This document explains how to set up Google OAuth authentication for the NeuTranscriber application.

## Backend Setup (Python/Flask)

### 1. Database Setup ✅
PostgreSQL database `neutranscriber_db` has been created and is ready to use.

### 2. New Files Created

#### `models.py`
Contains two SQLAlchemy models:
- **User**: Stores Google-authenticated users
  - Fields: id, email, google_id, name, picture_url, created_at, last_login
  - Methods: `to_dict()` for JSON serialization
  
- **Transcription**: Stores user transcription history
  - Fields: id, user_id (FK), filename, original_filename, midi_filename, status, error_message, processing_time, created_at, completed_at
  - Methods: `to_dict()` for JSON serialization

#### `auth.py`
Authentication routes blueprint with three endpoints:

- **POST /auth/google/callback**
  - Receives Google ID token from frontend
  - Verifies token with Google's servers
  - Creates or updates user in database
  - Returns JWT access token and refresh token
  - Request: `{ "token": "<google_id_token>" }`
  - Response: `{ "access_token": "...", "refresh_token": "...", "user": {...} }`

- **POST /auth/logout**
  - Simple endpoint for frontend to call on logout
  - Returns success message

- **POST /auth/refresh**
  - Refreshes JWT access token using refresh token
  - Request: Authorization header with refresh token
  - Response: `{ "access_token": "..." }`

### 3. Modified Files

#### `app.py`
- Added database initialization with SQLAlchemy
- Added JWT manager configuration
- Loaded environment variables from `.env` file
- Registered auth blueprint
- Updated `/api/transcribe` endpoint to require JWT authentication
- Updated `/api/transcribe` to save transcription records to database
- Added `db.create_all()` in main block to create tables on startup

#### `requirements.txt`
Added new dependencies:
- Flask-SQLAlchemy==3.1.1
- flask-jwt-extended==4.7.1
- psycopg2-binary==2.9.10
- python-dotenv==1.2.1
- google-auth-oauthlib==1.2.2

### 4. Environment Configuration

Create a `.env` file in the `neutranscriber-server/` directory:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production

# Database Configuration
DATABASE_URL=postgresql://henrywang@localhost:5432/neutranscriber_db

# Environment
FLASK_ENV=development
DEBUG=True
```

**How to get Google credentials:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google+ API
4. Create OAuth 2.0 credentials (Web application type)
5. Add authorized JavaScript origins: `http://localhost:3000`
6. Add authorized redirect URIs: `http://localhost:3000/auth/callback`
7. Copy Client ID and Client Secret into `.env`

### 5. Install Dependencies

```bash
cd neutranscriber-server
pip install -r requirements.txt
```

### 6. Running the Backend

```bash
python app.py
```

The app will:
1. Load environment variables from `.env`
2. Create database tables if they don't exist
3. Initialize SQLAlchemy, JWT, and WebSocket connections
4. Listen on `http://localhost:9000`

## Frontend Setup (React)

### 1. Install Google OAuth Library

```bash
cd ../neutranscriptor-web
npm install @react-oauth/google
```

### 2. Wrap App with Google OAuth Provider

Update `src/App.js`:

```javascript
import { GoogleOAuthProvider } from '@react-oauth/google';

function App() {
  return (
    <GoogleOAuthProvider clientId={process.env.REACT_APP_GOOGLE_CLIENT_ID}>
      {/* Your app components */}
    </GoogleOAuthProvider>
  );
}
```

### 3. Create Login Component

Create `src/components/GoogleLogin.js`:

```javascript
import { useGoogleLogin } from '@react-oauth/google';
import { useContext } from 'react';
import { useNavigate } from 'react-router-dom';

export function GoogleLoginButton() {
  const navigate = useNavigate();
  
  const login = useGoogleLogin({
    onSuccess: async (codeResponse) => {
      try {
        const response = await fetch('http://localhost:9000/auth/google/callback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: codeResponse.access_token })
        });
        
        if (response.ok) {
          const data = await response.json();
          // Store tokens in localStorage
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          localStorage.setItem('user', JSON.stringify(data.user));
          
          // Redirect to dashboard
          navigate('/dashboard');
        }
      } catch (error) {
        console.error('Login failed:', error);
      }
    },
    flow: 'implicit', // or use 'auth-code-with-pkce' for production
  });
  
  return (
    <button onClick={() => login()}>
      Sign in with Google
    </button>
  );
}
```

### 4. Create Context for Auth

Create `src/contexts/AuthContext.js`:

```javascript
import { createContext, useState, useEffect } from 'react';

export const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  
  useEffect(() => {
    // Check for stored token on mount
    const stored = localStorage.getItem('access_token');
    const userData = localStorage.getItem('user');
    
    if (stored && userData) {
      setToken(stored);
      setUser(JSON.parse(userData));
    }
  }, []);
  
  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    setUser(null);
    setToken(null);
  };
  
  return (
    <AuthContext.Provider value={{ user, token, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
```

### 5. Create Protected Route Component

```javascript
import { useContext } from 'react';
import { Navigate } from 'react-router-dom';
import { AuthContext } from '../contexts/AuthContext';

export function ProtectedRoute({ component: Component }) {
  const { token } = useContext(AuthContext);
  
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  
  return <Component />;
}
```

### 6. Update AudioUpload to Use Auth

In `src/components/AudioUpload.js`:

```javascript
const uploadFile = async (file) => {
  const token = localStorage.getItem('access_token');
  
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch('http://localhost:9000/api/transcribe', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });
  
  const data = await response.json();
  return data;
};
```

### 7. Environment Variables

Create `.env` in `neutranscriptor-web/`:

```
REACT_APP_GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
REACT_APP_API_URL=http://localhost:9000
```

### 8. Frontend Environment File

Update `package.json` scripts to load env:

```json
"start": "react-scripts start",
"build": "react-scripts build",
"test": "react-scripts test",
```

## Testing the Flow

### Backend Testing

1. **Create tables:**
   ```bash
   cd neutranscriber-server
   python app.py
   # Tables will be created automatically on first run
   ```

2. **Test the health endpoint:**
   ```bash
   curl http://localhost:9000/api/health
   ```

3. **Generate a test Google token** (use Google OAuth playground):
   - Go to https://developers.google.com/oauthplayground/
   - Configure it with your Google Client ID/Secret
   - Get an ID token

4. **Test the auth endpoint:**
   ```bash
   curl -X POST http://localhost:9000/auth/google/callback \
     -H "Content-Type: application/json" \
     -d '{"token": "your-google-token"}'
   ```

### Frontend Testing

1. **Start the React app:**
   ```bash
   npm start
   ```

2. **Click Google Login button**

3. **Verify JWT tokens stored in localStorage:**
   ```javascript
   // In browser console
   console.log(localStorage.getItem('access_token'));
   console.log(localStorage.getItem('user'));
   ```

4. **Test protected API call:**
   ```javascript
   fetch('http://localhost:9000/api/transcribe', {
     method: 'POST',
     headers: {
       'Authorization': 'Bearer ' + localStorage.getItem('access_token')
     },
     body: formData
   })
   ```

## Database Schema

### users table
```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(120) UNIQUE NOT NULL,
  google_id VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(120),
  picture_url VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
```

### transcriptions table
```sql
CREATE TABLE transcriptions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  filename VARCHAR(255) NOT NULL,
  original_filename VARCHAR(255),
  midi_filename VARCHAR(255),
  status VARCHAR(50) DEFAULT 'PENDING',
  error_message VARCHAR(500),
  processing_time FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP
);

CREATE INDEX idx_transcriptions_user_id ON transcriptions(user_id);
CREATE INDEX idx_transcriptions_created_at ON transcriptions(created_at);
```

## Security Notes

1. **In Production:**
   - Use HTTPS/WSS only
   - Set `JWT_SECRET_KEY` to a strong random value
   - Set `FLASK_ENV=production`
   - Don't commit `.env` file to git
   - Use environment variable management tools (e.g., AWS Secrets Manager)

2. **Token Management:**
   - Access tokens expire in 24 hours
   - Use refresh tokens to get new access tokens
   - Store tokens securely (httpOnly cookies preferred over localStorage)

3. **CORS:**
   - Currently allows all origins for development
   - In production, restrict to your domain

4. **Database:**
   - Add SSL to PostgreSQL connection
   - Use connection pooling for production
   - Regular backups

## Troubleshooting

**"Invalid token" error:**
- Verify GOOGLE_CLIENT_ID in `.env` matches your Google Console project
- Check token hasn't expired
- Ensure token is a valid Google ID token (not access token)

**Database connection errors:**
- Verify PostgreSQL is running: `psql -U henrywang -d neutranscriber_db`
- Check DATABASE_URL in `.env`
- Ensure `neutranscriber_db` exists

**CORS errors:**
- Add frontend origin to Google Cloud Console authorized origins
- Verify Flask-CORS headers in response

**JWT errors:**
- Clear localStorage and re-login
- Check JWT_SECRET_KEY is set in `.env`
- Verify token in Authorization header format: `Bearer <token>`

## Next Steps

1. ✅ Backend API ready with auth endpoints
2. ⏳ Frontend Google Login component
3. ⏳ Protected routes with auth context
4. ⏳ User dashboard showing transcription history
5. ⏳ User profile management
6. ⏳ End-to-end testing
