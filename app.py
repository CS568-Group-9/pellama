import base64
import dataclasses
import datetime
from enum import Enum
import json
import os
import random
import uuid
from dataclasses import dataclass
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

app = Flask(__name__)
session_id = uuid.uuid4()

class PromptSource(Enum):
    MANUAL = 0
    PROMPT_ONE = 1
    PROMPT_ALL = 2
    def __int__(self):
        return self.value

@dataclass
class PromptReponse:
    prompt: str = None
    response: str = None

@dataclass
class UserConversation:
    initial: PromptReponse = None
    feedback: str = None
    manual: str = None
    revised: list[PromptReponse] = None
    idxSelect: int = -1

state: list[UserConversation] = []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST' and len(state) == 0 and request.form['prompt_msg']:
        prompt_msg = request.form['prompt_msg']
        url = dalleImg(prompt_msg)

        uc = UserConversation()
        uc.initial = PromptReponse(prompt_msg, url)
        state.append(uc)
        
        dump_state(state)
        return redirect('/feedback')

    return render_template('index.html')

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    try:
        cur_uc = state[-1]
    except IndexError:
        return redirect('/')

    if request.method == 'POST' and request.form['feedback_msg']:
        feedback_msg = request.form['feedback_msg']
        cur_uc.feedback = feedback_msg
        dump_state(state)
        return redirect('/manualfix')

    return render_template('feedback.html', cur_uc=cur_uc)

@app.route('/manualfix', methods=['GET', 'POST'])
def manualfix():
    try:
        cur_uc = state[-1]
    except IndexError:
        return redirect('/')

    if request.method == 'POST' and request.form['manualfix_msg']:
        manualfix_msg = request.form['manualfix_msg']
        cur_uc.manual = manualfix_msg

        one_gpt_prompt = gptPrompt(historical=False)
        all_gpt_prompt = gptPrompt(historical=True)

        promptInfos = [
            {
                'prompt': cur_uc.manual,
                'ps': PromptSource.MANUAL,
            },
            {
                'prompt': one_gpt_prompt,
                'ps': PromptSource.PROMPT_ONE,
            },
            {
                'prompt': all_gpt_prompt,
                'ps': PromptSource.PROMPT_ALL,
            },
        ]

        cur_uc.revised = [None] * len(promptInfos) 
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Start the load operations and mark each future with its URL
            future_to_pi = {executor.submit(dalleImg, pi['prompt']): pi for pi in promptInfos}
            for future in as_completed(future_to_pi):
                try:
                    pi = future_to_pi[future]
                    img = future.result()
                    cur_uc.revised[int(pi['ps'])] = PromptReponse(pi['prompt'], img)
                except Exception as exc:
                    print('Exception: %s' % (exc))

        dump_state(state)
        return redirect('/selection')

    return render_template('manualfix.html', cur_uc=cur_uc)

@app.route('/selection', methods=['GET', 'POST'])
def selection():
    try:
        cur_uc = state[-1]
    except IndexError:
        return redirect('/')

    if request.method == 'POST' and request.form['img_selection']:
        img_selection = request.form['img_selection']
        cur_uc.idxSelect = int(img_selection)

        uc = UserConversation()
        uc.initial = cur_uc.revised[cur_uc.idxSelect]
        state.append(uc)
        
        dump_state(state)
        return redirect('/feedback')

    choices = list(enumerate(cur_uc.revised))
    random.shuffle(choices)
    return render_template('selection.html', cur_uc=cur_uc, choices=choices)

@app.route('/historical', methods=['GET'])
def historical():
    try:
        cur_uc = state[-1]
    except IndexError:
        return redirect('/')
    
    dump_state(state)

    return render_template('historical.html', state=state, psMap={i.value: i.name for i in PromptSource})

def dump_state(state):
    out_obj = {
        'sessionId': str(session_id),
        'createdAt': datetime.datetime.now().isoformat(),
        'state': state,
    }
    out = json.dumps(out_obj, cls=JSONEncoder) + '\n'
    with open('./session_results.jsonl', 'a+t') as f:
        f.write(out)

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

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

def gptPrompt(historical=False):
    cur_uc, rest = state[-1], state[:-1]

    feedback = cur_uc.feedback
    initial_prompt = cur_uc.initial.prompt
    img_url = cur_uc.initial.response

    base64_image = encode_image(img_url)

    content_arr = [
                {"type": "text", "text": f"""
                {feedback}
                What could I use as a DALLE-3 prompt to make the image below better? 
                Return only the prompt to generate the image, and do not use overly descriptive language unless instructed.
                Do not surround the returned prompt with quotes.
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
            ]
    
    if historical and rest:
        content_arr.append(
                {"type": "text", "text": f"""
                As follows is a series of image generating prompts, the images generated for the prompts, and the user feedbacks to change the prompt, in that order,
                starting from the first generated to the most recent iteration. Use these historical responses to improve the prompt suggestion.
                """
                })
    
        for uc in rest:
            content_arr.append({"type": "text", "text": f"""Prompt: "{uc.initial.prompt}" """})
            content_arr.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_image(uc.initial.response)}",
                            "detail": "low"
                        },
                    })
            content_arr.append({"type": "text", "text": f"""Feedback: "{uc.feedback}" """})

    response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[
        {
            "role": "user",
            "content": content_arr,
        }
    ],
    max_tokens=600,
    )

    return response.choices[0].message.content

if __name__ == '__main__':
    app.run(debug=True)