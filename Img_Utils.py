from PIL import Image
import io
import requests

def download_image(url):
    response = requests.get(url)
    return Image.open(io.BytesIO(response.content))

def add_speech_bubble(image, bubble_position=(0, 0)):
    bubble = Image.open('DATA/bubble.jpg')  # Load your speech bubble image
    bubble = bubble.resize((image.width, int(image.height * 0.2)))

    # Position the bubble at the top of the image
    image.paste(bubble, bubble_position, bubble)

    return image

def create_gif_from_image(image, duration=100):
    frames = [image] * 10
    gif = io.BytesIO()
    frames[0].save(gif,
                   format='GIF',
                   save_all=True,
                   append_images=frames[1:],
                   loop=0,
                   duration=duration)
    gif.seek(0)
    return gif

async def find_image_url(channel, user):
    async for message in channel.history(limit=100):
        if message.author == user:
            if 'media.discordapp.net/attachments' in message.content or any(
                    ext in message.content.lower()
                    for ext in ['png', 'jpg', 'jpeg', 'webp']):
                return message.content

            for attachment in message.attachments:
                if 'media.discordapp.net/attachments' in attachment.url or any(
                        ext in attachment.url.lower()
                        for ext in ['png', 'jpg', 'jpeg', 'webp']):
                    return attachment.url

            for embed in message.embeds:
                if embed.image and embed.image.url:
                    if 'media.discordapp.net/attachments' in embed.image.url or any(
                            ext in embed.image.url.lower()
                            for ext in ['png', 'jpg', 'jpeg', 'webp']):
                        return embed.image.url
    return None

async def process_image(channel, user, bubble_position=(0, 0)):
    url = await find_image_url(channel, user)
    if url:
        image = download_image(url)
        image_with_bubble = add_speech_bubble(image, bubble_position)
        gif = create_gif_from_image(image_with_bubble)
        return gif
    return None
