"""Start Flask and expose it publicly through Ngrok for demos/testing."""
import os
from pyngrok import ngrok
from app import create_app

PORT = 5000

if __name__ == "__main__":
    token = os.getenv("NGROK_AUTHTOKEN")
    if token:
        ngrok.set_auth_token(token)
    tunnel = ngrok.connect(PORT)
    print(f"\n Public URL: {tunnel.public_url}\n")
    create_app().run(port=PORT, debug=False, use_reloader=False)
