from PIL import Image
import os

def init(client):
    global image_client
    image_client = client

def analyze_image_prompt(image_path: str, prompt: str, model: str = "gemini-3.5-flash-lite") -> str:
    """Send an image + prompt to a specified Gemini model, return its text answer."""
    if not os.path.exists(image_path):
        return f"Error: file not found: {image_path}"

    img = Image.open(image_path)

    response = image_client.models.generate_content(
        model=model,
        contents=[img, prompt],
    )

    return response.text


def analyze_image(image_path: str):
    """Load an image and return it directly as a PIL Image for injection into the chat model's context."""

    if not os.path.exists(image_path):
        return f"Error: file not found: {image_path}"

    return Image.open(image_path)