from pinference import PianoTranscription, sample_rate, load_audio
from werkzeug.utils import secure_filename
from flask import Flask, flash, request, redirect, url_for, render_template
import time
import os
from flask import Flask

app = Flask(__name__)
app.secret_key = "secret key"
app.config['UPLOAD_FOLDER'] = 'static/mp3/'
app.config['STORE_FOLDER'] = 'static/midi/'

# ALLOWED_EXTENSIONS = set(['mp3', 'mid', 'mp4'])
ALLOWED_EXTENSIONS = set(['mp3'])


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def wrapper(func):
    def inner(*args, **kwargs):
        return func(*args, **kwargs)
    return inner


@app.route('/', methods=['GET'],  endpoint='upload_mp3')
@wrapper
def upload_mp3():
    return render_template('upload.html')


@app.route('/transcript/', methods=['GET', 'POST'], endpoint='upload_transcript')
@wrapper
def upload_transcript():
    if 'file' not in request.files:
        flash('No MP3 file part.')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('No a mp3 file selected for uploading.')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(
            os.getcwd(), app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        print('upload_image filename: ' + filename)
        flash('The MP3 file is successfully uploaded and displayed below.')

        # Implement Inference
        output_midi_path = os.path.join(
            os.getcwd(), app.config['STORE_FOLDER'], filename.replace('.mp3', '.mid'))
        print('MP3 File Path: ' + filepath)
        print('MIDI File Path: ' + output_midi_path)
        flash('Start transcripting...')
        inference(audio_path=filepath, output_midi_path=output_midi_path)
        flash('Transcription completed.')
        return render_template('upload.html', filename=filename, midiname=filename.replace('.mp3', '.mid'))


@app.route('/mp3/<filename>/', methods=['GET'], endpoint='display_mp3')
@wrapper
def display_mp3(filename):
    # print('display_mp3: ' + filename)
    return redirect(url_for('static', filename='mp3/' + filename), code=301)


@app.route('/midi/<filename>/', methods=['GET'], endpoint='display_midi')
@wrapper
def display_midi(filename):
    # print('display_midi: ' + filename)
    return redirect(url_for('static', filename='midi/' + filename), code=301)


def inference(audio_path, output_midi_path):
    """Inference template.
    Args:
    model_type: str
    audio_path: str
    """
    # # Arugments & parameters
    # audio_path = args.audio_path
    # output_midi_path = args.output_midi_path
    # device = 'cuda' if args.cuda and torch.cuda.is_available() else 'cpu'
    device = 'cpu'

    # Load audio
    (audio, _) = load_audio(audio_path, sr=sample_rate, mono=True)

    # Transcriptor
    transcriptor = PianoTranscription(device=device, checkpoint_path=None)
    """device: 'cuda' | 'cpu'
        checkpoint_path: None for default path, or str for downloaded checkpoint path.
        """
    # Transcribe and write out to MIDI file
    transcribe_time = time.time()
    transcribed_dict = transcriptor.transcribe(audio, output_midi_path)
    print('Transcribe time: {:.3f} s'.format(time.time() - transcribe_time))


if __name__ == "__main__":
    # 调试本应用时
    # app.run()
    # 运行本程序时，需要指定 IP 地址
    app.run(debug=False, host='0.0.0.0', port=9075)
