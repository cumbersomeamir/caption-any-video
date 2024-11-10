import os
import openai
import requests
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip

# API keys from environment variables
openai_api_key = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAI client
client = openai.OpenAI(api_key=openai_api_key)

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
    print("The transcription object is ", transcription)
    return transcription  # Return the full transcription for further processing

# Function to create captions as text clips and overlay them on the video
def add_captions_to_video(video_path, transcription_data, output_path="video_with_captions.mp4"):
    video = VideoFileClip(video_path)
    video = video.set_audio(video.audio)  # Ensure original audio is included
    captions = []

    # Iterate over each word in the transcription and add it as a caption with timestamp
    for word_info in transcription_data.words:
        word = word_info.word
        start_time = word_info.start
        end_time = word_info.end

        # Create a text clip for each word with much larger font size
        text_clip = (TextClip(word, fontsize=100, color='white', stroke_color='black', stroke_width=3)
                     .set_position('center')  # Center the text
                     .set_start(start_time)
                     .set_duration(end_time - start_time))

        # Add a larger solid background rectangle using ColorClip
        bg_clip = (ColorClip(size=(text_clip.w + 80, text_clip.h + 80), color=(0, 0, 0))  # Much larger black background
                   .set_opacity(0.6)  # Semi-transparent
                   .set_position('center')
                   .set_start(start_time)
                   .set_duration(end_time - start_time))

        captions.extend([bg_clip, text_clip])  # Add both background and text to captions

    # Combine the original video with all text and background clips (captions)
    final_video = CompositeVideoClip([video, *captions])

    # Write the final video with captions and audio
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
    print("Video with captions saved as:", output_path)

# Main function to process the video, transcribe, and add captions
def transcribe_and_caption_video(video_url):
    # Step 1: Download the video
    video_path = download_video(video_url)

    # Step 2: Extract audio from the video
    audio_path = extract_audio(video_path)

    # Step 3: Get the transcription
    transcription_data = speech_to_text(audio_path)

    # Step 4: Add captions to the video
    add_captions_to_video(video_path, transcription_data)

# Sample usage
video_url = "https://mygenerateddatabucket.s3.eu-north-1.amazonaws.com/videos/dcc10be0-9fde-4ea7-8cf2-a214532a52b5.mp4"
transcribe_and_caption_video(video_url)
