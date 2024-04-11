# %%
import base64
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

# Function to encode the image
def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')


# %% [markdown]
# Dall-e-3 image generation here

# %%
response = client.images.generate(
  model="dall-e-3",
  prompt="Fantasy landscape inspired by Middle Earth's Isengard during the Mordor invasion, featuring a dramatic but smooth red sky and gently rolling mountains without sharp peaks, surrounded by lush forests and a serene river flowing through the valley, under a soothing, diffuse light.",
  size="1024x1024",
  quality="standard",
  n=1,
)

print(response.data[0].url)

# %% [markdown]
# GPT-4V Request with text and images

# %%
# Path to your image
image_path = "./examples/oai_image_example.png"

# Getting the base64 string
base64_image = encode_image(image_path)

response = client.chat.completions.create(
  model="gpt-4-turbo",
  messages=[
    {
      "role": "user",
      "content": [
        {"type": "text", "text": """
          I dont like the swirling clouds in this image, and I don't like how sharp the mountains are in the scene. 
          What could I use as a DALLE-3 prompt to make the image below better? 
          The prompt to generate the image below was: "middle earth isengard but the sky is red from the mordor invasion" 
        """},
        {
          "type": "image_url",
          "image_url": {
            "url": f"data:image/jpeg;base64,{base64_image}",
            "detail": "low"
          },
        },
      ],
    }
  ],
  max_tokens=300,
)

print(response.choices[0].message.content)

# %%
# completion = client.chat.completions.create(
#   model="gpt-4",
#   messages=[
#     {"role": "system", "content": "You are a helpful assistant."},
#     {"role": "user", "content": """Write me a paragraph with this as a theme "middle earth isengard but the sky is red from the mordor invasion" """}
#   ]
# )

# print(completion)



