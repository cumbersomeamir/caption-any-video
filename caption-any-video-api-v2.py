import os
import openai
import requests
import boto3
from flask import Flask, request, jsonify
from botocore.exceptions import NoCredentialsError
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})


# AWS and OpenAI configuration from environment variables
aws_access_key = os.getenv("AWS_ACCESS_KEY")
aws_secret_key = os.getenv("AWS_SECRET_KEY")
s3_bucket_name = os.getenv("S3_BUCKET_NAME")
aws_region = os.getenv("AWS_REGION")  # e.g., 'us-east-1'
openai_api_key = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAI client
client = openai.OpenAI(api_key=openai_api_key)

app = Flask(__name__)

# Function to download the video from a URL
def download_video(url, save_path="video.mp4"):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as video_file:
            for chunk in response.iter_content(chunk_size=8192):
                video_file.write(chunk)
        print("Video downloaded successfully.")
    else:
        print("Failed to download video.")
    return save_path

# Function to extract audio from the video
def extract_audio(video_path, audio_path="audio.mp3"):
    video = VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path)
    print("Audio extracted successfully.")
    return audio_path

# Function to transcribe the audio using Whisper API
def speech_to_text(mp3_path):
    audio_file = open(mp3_path, "rb")
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format='verbose_json',
        timestamp_granularities=['word']
    )
    print("The transcription text is", transcription.text)
    return transcription  # Return the full transcription for further processing

# Function to create captions as text clips and overlay them on the video
def add_captions_to_video(video_path, transcription_data, output_path="video_with_captions.mp4"):
    video = VideoFileClip(video_path)
    video = video.set_audio(video.audio)  # Ensure original audio is included
    captions = []

    # Set font size and padding based on video dimensions
    video_height = video.size[1]
    if video_height >= 1080:  # 1080p and higher
        font_size = 40
        padding = 30
    elif video_height >= 720:  # HD resolution
        font_size = 30
        padding = 20
    else:  # Lower resolution
        font_size = 20
        padding = 10

    # Iterate over each word in the transcription and add it as a caption with timestamp
    for word_info in transcription_data.words:
        word = word_info.word
        start_time = word_info.start
        end_time = word_info.end

        # Create a text clip for each word with a dynamic font size
        text_clip = (TextClip(word, fontsize=font_size, color='white', stroke_width=3)
                     .set_position('center')  # Center the text
                     .set_start(start_time)
                     .set_duration(end_time - start_time))

        # Add a background rectangle using ColorClip with dynamic padding
        bg_clip = (ColorClip(size=(text_clip.w + padding, text_clip.h + padding), color=(0, 0, 0))  # Black background
                   .set_opacity(0.8)  # Semi-transparent
                   .set_position('center')
                   .set_start(start_time)
                   .set_duration(end_time - start_time))

        captions.extend([bg_clip, text_clip])  # Add both background and text to captions

    # Combine the original video with all text and background clips (captions)
    final_video = CompositeVideoClip([video, *captions])
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
    return output_path

# Function to upload video to S3
def upload_file_to_s3(file_path, bucket_name, s3_filename):
    s3 = boto3.client('s3',
                      region_name=aws_region,
                      aws_access_key_id=aws_access_key,
                      aws_secret_access_key=aws_secret_key)

    try:
        s3.upload_file(file_path, bucket_name, s3_filename)
        s3_url = f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{s3_filename}"
        print(f"File uploaded to {s3_url}")
        return s3_url
    except FileNotFoundError:
        print("The file was not found")
        return None
    except NoCredentialsError:
        print("Credentials not available")
        return None

# Flask route to handle video processing and upload
@app.route('/caption_video', methods=['POST'])
def process_video():
    data = request.get_json()
    video_url = data.get('video_url')
    
    if not video_url:
        return jsonify({"error": "Video URL is required"}), 400
    
    # Step 1: Download the video
    video_path = download_video(video_url)

    # Step 2: Extract audio from the video
    audio_path = extract_audio(video_path)

    # Step 3: Get the transcription
    transcription_data = speech_to_text(audio_path)

    # Step 4: Add captions to the video
    output_video_path = "video_with_captions.mp4"
    add_captions_to_video(video_path, transcription_data, output_video_path)

    # Step 5: Upload the final video with captions to S3
    s3_filename = "final_video_with_captions.mp4"
    s3_url = upload_file_to_s3(output_video_path, s3_bucket_name, s3_filename)

    if s3_url:
        return jsonify({"video_url": s3_url}), 200
    else:
        return jsonify({"error": "Failed to upload video to S3"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=7020)
