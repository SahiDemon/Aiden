import asyncio
import urllib.parse
import httpx
import webbrowser

# ------------------------------------------------------------------------------
# CONFIGURATION - PASTE YOUR CREDENTIALS HERE OR INPUT WHEN PROMPTED
# ------------------------------------------------------------------------------
CLIENT_ID = ""      # Paste your Client ID here if you want
CLIENT_SECRET = ""  # Paste your Client Secret here if you want
REDIRECT_URI = "http://127.0.0.1:8888/callback"

# Scopes required for Aiden
SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-library-read",  # For liked songs
    "playlist-read-private",
    "playlist-read-collaborative"
]

async def get_token():
    print("="*60)
    print("Spotify Refresh Token Generator")
    print("="*60)
    
    c_id = CLIENT_ID or input("Enter your Spotify Client ID: ").strip()
    c_secret = CLIENT_SECRET or input("Enter your Spotify Client Secret: ").strip()
    
    if not c_id or not c_secret:
        print("Error: Client ID and Secret are required.")
        return

    # 1. Generate Authorization URL
    params = {
        "client_id": c_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    auth_url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"
    
    print("\n1. Opening browser to authorize app...")
    print(f"   URL: {auth_url}")
    webbrowser.open(auth_url)
    
    print("\n2. After authorizing, you will be redirected to a URL like:")
    print(f"   {REDIRECT_URI}?code=...")
    print("   (It might show a 'Site can't be reached' error - that's fine!)")
    
    redirect_response = input("\n3. Paste the FULL URL you were redirected to here: ").strip()
    
    # 2. Parse Authorization Code
    try:
        parsed = urllib.parse.urlparse(redirect_response)
        query_params = urllib.parse.parse_qs(parsed.query)
        code = query_params["code"][0]
    except Exception:
        print("\n❌ Error: Could not extract 'code' from the URL. Make sure you pasted the full URL.")
        return

    # 3. Exchange Code for Tokens
    print("\n4. Exchanging code for tokens...")
    
    token_url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                token_url, 
                data=data, 
                auth=(c_id, c_secret)
            )
            response.raise_for_status()
            tokens = response.json()
            
            print("\n" + "="*60)
            print("✅ SUCCESS! Here are your credentials:")
            print("="*60)
            print(f"\nSPOTIFY_CLIENT_ID={c_id}")
            print(f"SPOTIFY_CLIENT_SECRET={c_secret}")
            print(f"SPOTIFY_REFRESH_TOKEN={tokens['refresh_token']}")
            print("\n" + "="*60)
            print("Copy these lines into your .env file.")
            
        except httpx.HTTPStatusError as e:
            print(f"\n❌ Error getting tokens: {e.response.text}")
        except Exception as e:
            print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    # Install httpx if missing
    try:
        import httpx
    except ImportError:
        print("Installing httpx...")
        import os
        os.system("pip install httpx")
        import httpx

    asyncio.run(get_token())
