"""
Install the Google AI Python SDK

$ pip install google-generativeai

See the getting started guide for more information:
https://ai.google.dev/gemini-api/docs/get-started/python
"""

from email.mime import image
from pathlib import Path
from cv2 import add
import google.generativeai as genai

genai.configure(api_key="")


def upload_to_gemini(path, mime_type=None):
    """Uploads the given file to Gemini.

    See https://ai.google.dev/gemini-api/docs/prompting_with_media
    """
    img = Path(r"H:\lora\素材リスト\スクリプト\testimg\1_img\file01.png")
    file = genai.upload_file(img, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file


# Create the model
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    # safety_settings = Adjust safety settings
    # See https://ai.google.dev/gemini-api/docs/safety-settings
)

# TODO Make these files available on the local file system
# You may need to update the file paths
files = [
    upload_to_gemini("1tbUap7h2i7r99pWHybVGqxJEGYZJ3nWy", mime_type="application/octet-stream"),
    upload_to_gemini("1yO-tWgqc7nCwoOFrIOfFZfJMAxi_GIFM", mime_type="application/octet-stream"),
    upload_to_gemini("1L7Q-gJSXYq60TRWUTk5W8txYYKbfVNAY", mime_type="application/octet-stream"),
]

prompt = "A"
add_prompt = "A"
image = "image/webp: "

prompt_parts = [
    f"{prompt}",
    "image/webp: ",
    "",
    'formatJSON: {"tags": "Tag1, Tag2, Tag3",  "caption": "This is the caption."}',
    "ADDITIONAL_PROMPT: Korean girl in a comic book.",
    'TagsANDCaption: {"tags": "dress, long hair, text, sitting, black hair, blue eyes, heterochromia, flower, high heels, two-tone hair, armpits, elbow gloves, red eyes, boots, gloves, white hair, hat flower, nail polish, panties, red rose, pantyshot, purple nails, rose petals, looking at viewer, hat, navel, bare shoulders, choker, petals, red flower, cross-laced clothes, underwear, split-color hair, brown hair", "caption": "A stylish Korean girl, with heterochromia and a confident gaze, poses amidst scattered roses against a graffiti-marked wall, rendered in a vibrant comic book art style." }',
    "image/webp: ",
    "",
    'formatJSON: {"tags": "Tag1, Tag2, Tag3", "caption": "This is the caption."}',
    "ADDITIONAL_PROMPT: japanese idol",
    'TagsANDCaption: {"tags": "1girl, solo, long hair, brown hair, brown eyes, short sleeves, school uniform, white shirt, upper body, collared shirt, hair bobbles, blue bowtie, realistic, japanese, finger frame", "caption": "A young Japanese idol in a classic school uniform strikes a pose while performing, her energy and focus evident in her expression and hand gestures." }',
    "image/webp: ",
    "",
    'formatJSON: {"tags": "Tag1, Tag2, Tag3", "caption": "This is the caption."}',
    "ADDITIONAL_PROMPT: 1boy, tate eboshi, expressionless, fake horns, shoulder armor resembling onigawara with ornamental horns, 3d, full body, a person standing in a circle with their arms spread out., bridge, horizon, lake, mountain, ocean, planet, river, scenery, shore, snow, water, waterfall, solo, weapon, male focus, ornamental horn, white japanese armor, glowing, letterboxed, pillar, full armor, column, tree, outstretched arms, no humans, spread arms, animated character, fantasy setting, mysterious armor, ethereal glow, purple hues, virtual environment, crystals, otherworldly, long black hair, artistic filter, video game graphics, surreal atmosphere, front-facing pose, enigmatic expression, soft focus, virtual costume, obscured eyes, shoulder armor, arm bracers, magical ambiance, An animated fantasy character stands enigmatically in a surreal, crystal-laden environment, exuding a mystical presence as light softly radiates from their ethereal armor.",
    'TagsANDCaption: {"tags": "1boy, solo, tate eboshi, expressionless, fake horns, shoulder armor resembling onigawara with ornamental horns, 3d, full body, a person standing in a circle with their arms spread out., bridge, ornamental horn, white japanese armor, glowing, outstretched arms, fantasy setting, mysterious armor, ethereal glow, purple hues, otherworldly, long black hair, video game graphics, soft focus, obscured eyes, shoulder armor", "caption": "An animated fantasy character stands enigmatically in a surreal, crystal-laden environment, exuding a mystical presence as light softly radiates from their ethereal armor." }',
    "image/webp: ",
    f"{image}",
    'formatJSON: {"tags": "Tag1, Tag2, Tag3",\n "caption": "This is the caption."}',
    f"ADDITIONAL_PROMPT: {add_prompt}",
    "TagsANDCaption: ",
]

response = model.generate_content(prompt_parts)

print(response.text)
