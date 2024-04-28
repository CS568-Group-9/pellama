from flask import Flask, redirect, render_template, request

import base64
import os
from openai import OpenAI
from dotenv import load_dotenv
from urllib.request import urlopen

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

app = Flask(__name__)

class PromptReponse:
    prompt: str = None
    response: str = None
    def __init__(self, prompt, response):
        self.prompt = prompt
        self.response = response

class UserConversation:
    initial: PromptReponse = None
    feedback: str = None
    manual: str = None
    # 0 is feedback, 1 is manual
    revised: tuple[PromptReponse, PromptReponse] = None
    idxSelect = -1

state: list[UserConversation] = []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST' and len(state) == 0 and request.form['prompt_msg']:
        prompt_msg = request.form['prompt_msg']
        url = dalleImg(prompt_msg)
        print(f"Prompt: `{prompt_msg}`, Image: `{url}`")

        uc = UserConversation()
        uc.initial = PromptReponse(prompt_msg, url)
        state.append(uc)
        
        return redirect('/feedback')

    return render_template('index.html')

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    cur_uc = state[-1]
    if request.method == 'POST' and request.form['feedback_msg']:
        feedback_msg = request.form['feedback_msg']
        cur_uc.feedback = feedback_msg
        return redirect('/manualfix')

    return render_template('feedback.html', cur_uc=cur_uc)

@app.route('/manualfix', methods=['GET', 'POST'])
def manualfix():
    cur_uc = state[-1]
    if request.method == 'POST' and request.form['manualfix_msg']:
        manualfix_msg = request.form['manualfix_msg']
        cur_uc.manual = manualfix_msg

        manual_img = dalleImg(cur_uc.manual)
        gpt_prompt = gptPrompt(cur_uc.feedback, cur_uc.initial.prompt, cur_uc.initial.response)
        gpt_img = dalleImg(gpt_prompt)

        cur_uc.revised = (PromptReponse(cur_uc.manual, manual_img), PromptReponse(gpt_prompt, gpt_img))

        return redirect('/selection')

    return render_template('manualfix.html', cur_uc=cur_uc)

@app.route('/selection', methods=['GET', 'POST'])
def selection():
    cur_uc = state[-1]
    if request.method == 'POST':
        img_selection = request.form['img_selection']
        cur_uc.idxSelect = int(img_selection)

        uc = UserConversation()
        uc.initial = cur_uc.revised[cur_uc.idxSelect]
        state.append(uc)
        
        return redirect('/feedback')

    return render_template('selection.html', cur_uc=cur_uc)

# Function to encode the image
def encode_image(url):
  with urlopen(url) as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

def dalleImg(prompt: str):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )

    return response.data[0].url

def gptPrompt(feedback, initial_prompt, img_url):
    base64_image = encode_image(img_url)

    response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"""
                {feedback}
                What could I use as a DALLE-3 prompt to make the image below better? 
                Return only the prompt to generate the image, and do not use overly descriptive language unless instructed.
                The prompt to generate the image below was: "{initial_prompt}" 
                """
                },
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
    max_tokens=500,
    )

    return response.choices[0].message.content

if __name__ == '__main__':
    app.run(debug=True)