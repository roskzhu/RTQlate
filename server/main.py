from flask import Flask, request
from flask_cors import CORS, cross_origin
from openai import OpenAI
import cv2
from gaze_tracking import GazeTracking
import os
import requests
import json
import time
import assemblyai as aai
import subprocess
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

base_url = "https://api.assemblyai.com/v2"
headers = { "authorization": "9ab4969c17204b40bbb473f22b075eea" }
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

gaze = None
webcam = None

cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

@app.route("/summarize", methods=['POST'])
@cross_origin()
def summarize():
  request_data = request.get_json()
  presentation_text = request_data['text']
  completion = client.chat.completions.create(
    model="gpt-3.5-turbo-0125",
    messages=[{
      "role": "user",
		  "content": (f"Summarize the following content as much as possible into very, very brief flashcards for a presentation:\n{presentation_text}")
    }],
    temperature=0.9,
    max_tokens=200,
    top_p=1
  )
  content = completion.choices[0].message.content
  bullet_points = content.replace("\n", "").split("- ")
  bullet_points.pop(0)

  result = subprocess.run(['python', 'flashcard.py', json.dumps(bullet_points)], capture_output=True)
  return result.stdout

@app.route("/submit", methods=['POST'])
@cross_origin()
def submit():
  request_data = request.get_json()
  filename = request_data['filename']
  print(os.path.abspath(f"{os.path.expanduser('~')}/Downloads/{filename}"))
  # try to open the file for max 5 attempts, waiting 1 second in between each attempt
  response = None
  for i in range(5):
    print(f"Attempt {i}")
    try:
      with open(os.path.abspath(f"{os.path.expanduser('~')}/Downloads/{filename}"), "rb") as f:
        response = requests.post(base_url + "/upload", headers=headers, data=f)
        if response:
          break
    except:
      time.sleep(1)

  upload_url = response.json()["upload_url"]
  data = {
    "audio_url": upload_url,
    "auto_highlights": True,
    "sentiment_analysis": True,
  }
  url = base_url + "/transcript"
  response = requests.post(url, json=data, headers=headers)

  transcription_id = response.json()['id']
  polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcription_id}"

  transcription_result = None

  while True:
    transcription_result = requests.get(polling_endpoint, headers=headers).json()
    if transcription_result['status'] == 'completed':
      auto_highlights_result = transcription_result['auto_highlights_result']
      if auto_highlights_result:
        for highlight in auto_highlights_result['results']:
          print(f"Highlight: {highlight['text']}, Count: {highlight['count']}, Rank: {highlight['rank']}, Timestamps: {highlight['timestamps']}")
      break
    elif transcription_result['status'] == 'error':
      raise RuntimeError(f"Transcription failed: {transcription_result['error']}")
    else:
      time.sleep(3)
      
  return transcription_result

@app.route("/start-gaze-tracking", methods=['POST'])
@cross_origin()
def start_gaze_tracking():
  global gaze, webcam
  gaze = GazeTracking()
  webcam = cv2.VideoCapture(0)
  return ('', 204)

@app.route("/analyze-frame", methods=['GET'])
@cross_origin()
def analyze_frame():
  global gaze, webcam
  _, frame = webcam.read()
  gaze.refresh(frame)

  text = ""

  if gaze.is_right():
    text = "Looking right"
  elif gaze.is_left():
    text = "Looking left"
  elif gaze.is_center():
    text = "Looking center"

  left_pupil = gaze.pupil_left_coords()
  right_pupil = gaze.pupil_right_coords()

  return json.dumps({
    "direction": text, 
    "left_pupil": str(left_pupil), 
    "right_pupil": str(right_pupil),
    "horizontal_ratio": str(gaze.horizontal_ratio()),
    "vertical_ratio": str(gaze.vertical_ratio())
  })

@app.route("/stop-gaze-tracking", methods=['POST'])
@cross_origin()
def stop_gaze_tracking():
  global gaze, webcam
  webcam.release()
  cv2.destroyAllWindows()
  return ('', 204)
