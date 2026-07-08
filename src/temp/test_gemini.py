import google.generativeai as genai
import yaml
import os

def run_test():
    api_key = "AIzaSyCP3-DdoTQTuRavMLPnfuS6H6M_vowLIig"
    genai.configure(api_key=api_key)
    
    with open("config/prompts.yaml", "r", encoding="utf-8") as f:
        prompts = yaml.safe_load(f)
    
    system_prompt = prompts["system_prompt"]
    
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        generation_config={
            "temperature": 0.3,
            "max_output_tokens": 2000,
            "response_mime_type": "application/json",
            "top_p": 0.95,
            "top_k": 40,
        }
    )
    
    user_message = "turn off the fan and lock the computer"
    full_prompt = f"{system_prompt}\n\nUser: {user_message}\n\nRespond with valid JSON only."
    
    print("Sending request to Gemini...")
    response = model.generate_content(full_prompt)
    print("Raw Response:\n", response.text)

if __name__ == "__main__":
    run_test()
