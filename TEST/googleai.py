"""goofle AI studioを使用して画像のタグ付けを行うスクリプト
構造化プロンプトの使用
まだまだ使い方を寝る必要がある
"""

import toml
from pathlib import Path
import google.generativeai as genai

img0 = Path(r"your\path\to\img01.webp")
img1 = Path(r"your\path\to\img02.webp")
img2 = Path(r"your\path\to\img03.webp")

config = toml.load("processing.toml")
api_key = config["APIKEYS"]["google_api_key"]


# キーワード引数 api_key を使用して configure() を呼び出す
# キーワード引数しか受け取らない
genai.configure(api_key=api_key)

# Set up the model
generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 8192,
}

safety_settings = [
  {
    "category": "HARM_CATEGORY_HARASSMENT",
    "threshold": "BLOCK_NONE"
  },
  {
    "category": "HARM_CATEGORY_HATE_SPEECH",
    "threshold": "BLOCK_NONE"
  },
  {
    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "threshold": "BLOCK_NONE"
  },
  {
    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
    "threshold": "BLOCK_NONE"
  },
]

model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest",
                              generation_config=generation_config,
                              safety_settings=safety_settings)

prompt_parts = [
  "As an AI image tagging expert, your role is to provide accurate and specific tags for images to improve the CLIP model's performance. \nEach image should have tags that accurately capture its main subjects, setting, artistic style, composition, and technical details like image quality and camera settings. \nFor images of people, detail gender, attire, actions, pose, expressions, and any notable accessories. \nFor landscapes or objects, focus on the material, historical context, and any significant features. \nAlways use precise and specific tags—prefer \"gothic cathedral\" over \"building.\" Avoid duplicative tags. \nEach set of tags should be unique and relevant, separated only by commas, and kept within a 50-150 word count. \nAlso, provide a concise 1-2 sentence caption that captures the image's narrative or essence.",
  "input:img ",
  genai.upload_file(img0,mime_type="image/webp"),
  "Tags and Caption Tags:\n\nCaption:",
  "input:img ",
  genai.upload_file(img1,mime_type="image/webp"),
  "Tags and Caption Tags:\n\nCaption:",
  "input:img ",
  genai.upload_file(img2,mime_type="image/webp"),
  "Tags and Caption Tags:\n\nCaption:",
  "input:img ",
]

response = model.generate_content(prompt_parts)

# safety_ratings を出力
for candidate in response.candidates:
    print(f"Safety ratings: {candidate.safety_ratings}")

with open("Googleoutput.txt", "w") as f:
    f.write(response.text)
print(response.text)