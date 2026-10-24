import os

port = os.environ.get("PORT", "5000")
api_key = os.environ.get("API_KEY", "default_secret")
print(f"Server is listening on port {port}")
