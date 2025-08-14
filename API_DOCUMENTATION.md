# Neutranscriber Server API Documentation

## Overview

The Neutranscriber Server is a REST API service that converts audio files containing piano music into MIDI files. It uses advanced machine learning models for piano transcription and provides asynchronous processing through a queue-based system.

## Base URL

When running locally:
```
http://localhost:9000
```

## Authentication

No authentication is required for this API.

## Endpoints

### 1. Health Check

**Endpoint:** `GET /api/health`

**Description:** Simple health check to verify the service is running.

**Response:**
```json
{
  "status": "ok"
}
```

**Example:**
```bash
curl http://localhost:9000/api/health
```

---

### 2. Upload and Transcribe Audio

**Endpoint:** `POST /api/transcribe`

**Description:** Upload an audio file and start the piano transcription process. This is an asynchronous operation that returns immediately with a task ID.

**Request:**
- **Method:** POST
- **Content-Type:** multipart/form-data
- **Body:** Form data with a file field named `file`

**Supported Audio Formats:**
- MP3 (.mp3)
- WAV (.wav)
- FLAC (.flac)
- OGG (.ogg)
- M4A (.m4a)
- AIFF (.aiff)
- AAC (.aac)

**Response (Success):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Error):**
```json
{
  "error": "No file part in the request"
}
```

**Status Codes:**
- `202 Accepted` - File uploaded successfully, transcription started
- `400 Bad Request` - Invalid request (no file, empty filename, unsupported format)

**Example:**
```bash
# Upload an audio file for transcription
curl -X POST \
  -F "file=@path/to/your/piano_recording.mp3" \
  http://localhost:9000/api/transcribe
```

**Example Response:**
```json
{
  "task_id": "abc123-def456-ghi789"
}
```

---

### 3. Check Transcription Status

**Endpoint:** `GET /api/transcription_status/<task_id>`

**Description:** Check the status of a transcription task. Use this endpoint to poll for completion status.

**Path Parameters:**
- `task_id` (string, required) - The task ID returned from the transcribe endpoint

**Response States:**

**Pending:**
```json
{
  "state": "PENDING",
  "status": "Pending..."
}
```

**Success:**
```json
{
  "state": "SUCCESS",
  "result": {
    "status": "SUCCESS",
    "midi_filename": "abc123-def456-ghi789_piano_recording.mid",
    "transcription_time": 45.67
  }
}
```

**Failure:**
```json
{
  "state": "FAILURE",
  "status": "Error in transcription: File not found"
}
```

**Status Codes:**
- `200 OK` - Status retrieved successfully
- `400 Bad Request` - Invalid task ID

**Example:**
```bash
# Check status of transcription task
curl http://localhost:9000/api/transcription_status/abc123-def456-ghi789
```

---

### 4. Download MIDI File

**Endpoint:** `GET /api/download_midi/<filename>`

**Description:** Download the generated MIDI file after transcription is complete.

**Path Parameters:**
- `filename` (string, required) - The MIDI filename returned in the transcription result

**Response:**
- **Success:** Binary MIDI file download with `Content-Disposition: attachment`
- **Error:** JSON error message

**Status Codes:**
- `200 OK` - File downloaded successfully
- `404 Not Found` - File does not exist

**Example:**
```bash
# Download the generated MIDI file
curl -O http://localhost:9000/api/download_midi/abc123-def456-ghi789_piano_recording.mid
```

---

## Complete Workflow Example

Here's a complete example of how to use the API from start to finish:

### Step 1: Upload Audio File
```bash
# Upload your piano recording
response=$(curl -s -X POST \
  -F "file=@my_piano_song.mp3" \
  http://localhost:9000/api/transcribe)

# Extract task ID (requires jq for JSON parsing)
task_id=$(echo $response | jq -r '.task_id')
echo "Task ID: $task_id"
```

### Step 2: Poll for Completion
```bash
# Check status repeatedly until complete
while true; do
  status=$(curl -s http://localhost:9000/api/transcription_status/$task_id)
  state=$(echo $status | jq -r '.state')
  
  echo "Current state: $state"
  
  if [ "$state" = "SUCCESS" ]; then
    # Extract MIDI filename
    midi_filename=$(echo $status | jq -r '.result.midi_filename')
    echo "Transcription complete! MIDI file: $midi_filename"
    break
  elif [ "$state" = "FAILURE" ]; then
    echo "Transcription failed:"
    echo $status | jq -r '.status'
    break
  else
    echo "Still processing... waiting 5 seconds"
    sleep 5
  fi
done
```

### Step 3: Download MIDI File
```bash
# Download the generated MIDI file
curl -O http://localhost:9000/api/download_midi/$midi_filename
echo "MIDI file downloaded: $midi_filename"
```

---

## Python Example

Here's a complete Python example using the `requests` library:

```python
import requests
import time
import json

# Configuration
BASE_URL = "http://localhost:9000"
audio_file_path = "path/to/your/piano_recording.mp3"

def transcribe_piano_audio(audio_file_path):
    """Complete workflow to transcribe piano audio to MIDI"""
    
    # Step 1: Upload file
    print("Uploading audio file...")
    with open(audio_file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f"{BASE_URL}/api/transcribe", files=files)
    
    if response.status_code != 202:
        print(f"Upload failed: {response.json()}")
        return None
    
    task_id = response.json()['task_id']
    print(f"Upload successful. Task ID: {task_id}")
    
    # Step 2: Poll for completion
    print("Waiting for transcription to complete...")
    while True:
        response = requests.get(f"{BASE_URL}/api/transcription_status/{task_id}")
        status_data = response.json()
        state = status_data['state']
        
        print(f"Status: {state}")
        
        if state == 'SUCCESS':
            result = status_data['result']
            midi_filename = result['midi_filename']
            transcription_time = result['transcription_time']
            print(f"Transcription completed in {transcription_time} seconds!")
            print(f"MIDI filename: {midi_filename}")
            break
        elif state == 'FAILURE':
            print(f"Transcription failed: {status_data['status']}")
            return None
        else:
            time.sleep(5)  # Wait 5 seconds before checking again
    
    # Step 3: Download MIDI file
    print("Downloading MIDI file...")
    response = requests.get(f"{BASE_URL}/api/download_midi/{midi_filename}")
    
    if response.status_code == 200:
        # Save the MIDI file
        with open(midi_filename, 'wb') as f:
            f.write(response.content)
        print(f"MIDI file saved as: {midi_filename}")
        return midi_filename
    else:
        print(f"Download failed: {response.json()}")
        return None

# Usage
if __name__ == "__main__":
    midi_file = transcribe_piano_audio("my_piano_recording.mp3")
    if midi_file:
        print(f"Success! Generated MIDI file: {midi_file}")
```

---

## JavaScript/Node.js Example

```javascript
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');

const BASE_URL = 'http://localhost:9000';

async function transcribePianoAudio(audioFilePath) {
    try {
        // Step 1: Upload file
        console.log('Uploading audio file...');
        const form = new FormData();
        form.append('file', fs.createReadStream(audioFilePath));
        
        const uploadResponse = await axios.post(`${BASE_URL}/api/transcribe`, form, {
            headers: {
                ...form.getHeaders(),
            },
        });
        
        const taskId = uploadResponse.data.task_id;
        console.log(`Upload successful. Task ID: ${taskId}`);
        
        // Step 2: Poll for completion
        console.log('Waiting for transcription to complete...');
        while (true) {
            const statusResponse = await axios.get(`${BASE_URL}/api/transcription_status/${taskId}`);
            const statusData = statusResponse.data;
            const state = statusData.state;
            
            console.log(`Status: ${state}`);
            
            if (state === 'SUCCESS') {
                const result = statusData.result;
                const midiFilename = result.midi_filename;
                const transcriptionTime = result.transcription_time;
                console.log(`Transcription completed in ${transcriptionTime} seconds!`);
                console.log(`MIDI filename: ${midiFilename}`);
                
                // Step 3: Download MIDI file
                console.log('Downloading MIDI file...');
                const downloadResponse = await axios.get(`${BASE_URL}/api/download_midi/${midiFilename}`, {
                    responseType: 'stream'
                });
                
                const writer = fs.createWriteStream(midiFilename);
                downloadResponse.data.pipe(writer);
                
                return new Promise((resolve, reject) => {
                    writer.on('finish', () => {
                        console.log(`MIDI file saved as: ${midiFilename}`);
                        resolve(midiFilename);
                    });
                    writer.on('error', reject);
                });
                
            } else if (state === 'FAILURE') {
                console.log(`Transcription failed: ${statusData.status}`);
                return null;
            } else {
                await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds
            }
        }
    } catch (error) {
        console.error('Error:', error.message);
        return null;
    }
}

// Usage
transcribePianoAudio('my_piano_recording.mp3')
    .then(midiFile => {
        if (midiFile) {
            console.log(`Success! Generated MIDI file: ${midiFile}`);
        }
    });
```

---

## Error Handling

### Common Error Responses

**File Upload Errors:**
- `400 Bad Request` - No file provided, empty filename, or unsupported format
- `413 Payload Too Large` - File size exceeds server limits

**Task Status Errors:**
- `400 Bad Request` - Invalid or missing task ID

**File Download Errors:**
- `404 Not Found` - MIDI file doesn't exist (may have been cleaned up)

### Best Practices

1. **Polling Frequency:** Don't poll too frequently. A 5-second interval is recommended to avoid overwhelming the server.

2. **Timeout Handling:** Implement reasonable timeouts for long transcription jobs (typically 1-10 minutes depending on audio length).

3. **File Size Limits:** Be aware that larger audio files will take longer to process.

4. **Error Recovery:** Always check response status codes and handle errors gracefully.

5. **File Cleanup:** Download your MIDI files promptly as they may be cleaned up periodically.

---

## Technical Notes

- **Processing Time:** Transcription time varies based on audio length and complexity. Typical processing is 1-5x real-time.
- **Concurrent Jobs:** The server can handle multiple transcription jobs simultaneously.
- **File Storage:** Uploaded audio files and generated MIDI files are stored in the `static/` directory.
- **Model:** Uses the `piano_transcription_inference` library for state-of-the-art piano transcription.

---

## Setup and Running

Refer to the main README for setup instructions. The API runs on port 9000 by default and requires Redis for task queuing.
