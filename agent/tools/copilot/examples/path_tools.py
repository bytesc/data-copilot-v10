import string
import random

from agent.utils.get_config import config_data

STATIC_FOLDER = config_data.get('static_folder', 'tmp_imgs')


def generate_random_string(length=8):
    letters = string.ascii_lowercase
    random_string = ''.join(random.choice(letters) for _ in range(length))
    return random_string


def generate_img_path():
    return f"./{STATIC_FOLDER}/" + generate_random_string() + ".png"


def generate_html_path():
    return f"./{STATIC_FOLDER}/" + generate_random_string() + ".html"
