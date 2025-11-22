"""
Quick script to list available Gemini models
"""
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure with your API key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found in .env file")
    exit(1)

genai.configure(api_key=api_key)

print("Available Gemini Models:")
print("=" * 80)

try:
    # List all available models
    models = genai.list_models()
    
    for model in models:
        # Check if model supports generateContent
        if 'generateContent' in model.supported_generation_methods:
            print(f"\n✅ Model: {model.name}")
            print(f"   Display Name: {model.display_name}")
            print(f"   Description: {model.description}")
            print(f"   Supported Methods: {', '.join(model.supported_generation_methods)}")
            print(f"   Input Token Limit: {model.input_token_limit}")
            print(f"   Output Token Limit: {model.output_token_limit}")
            print("-" * 80)
            
except Exception as e:
    print(f"Error listing models: {e}")
    print("\nTrying alternative method...")
    
    # Try getting specific models
    try:
        test_models = [
            "gemini-pro",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "models/gemini-pro",
            "models/gemini-1.5-pro",
            "models/gemini-1.5-flash",
            "models/gemini-2.0-flash-exp"
        ]
        
        print("\nTesting specific models:")
        for model_name in test_models:
            try:
                model = genai.GenerativeModel(model_name)
                print(f"✅ {model_name} - Available")
            except Exception as e:
                print(f"❌ {model_name} - Not available: {str(e)[:100]}")
                
    except Exception as e2:
        print(f"Error in alternative method: {e2}")

print("\n" + "=" * 80)
print("Done!")
