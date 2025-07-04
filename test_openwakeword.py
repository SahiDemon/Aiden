#!/usr/bin/env python3
"""
Test openWakeWord models and capabilities
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

try:
    from openwakeword import Model
    import numpy as np
    print("✅ openWakeWord imported successfully")
except ImportError as e:
    print(f"❌ Failed to import openWakeWord: {e}")
    sys.exit(1)

def test_openwakeword_with_specific_models():
    """Test openWakeWord with specific model specifications"""
    print("🔧 Initializing openWakeWord with specific models...")
    
    try:
        # Try to initialize with common pre-trained models
        # On Windows, we need to use ONNX models
        print("📥 Attempting to load ONNX models...")
        
        # Try different initialization approaches
        approaches = [
            ("Default models", lambda: Model()),
            ("Hey Mycroft model", lambda: Model(wakeword_models=['hey_mycroft'])),
            ("Alexa model", lambda: Model(wakeword_models=['alexa'])),
            ("Empty init", lambda: Model(wakeword_models=[])),
        ]
        
        for name, init_func in approaches:
            try:
                print(f"\n🧪 Testing: {name}")
                oww = init_func()
                
                print(f"✅ {name} initialized successfully")
                
                # Get available models
                if hasattr(oww, 'models') and oww.models:
                    models = oww.models
                    print(f"📋 Models loaded ({len(models)}):")
                    for model_name in models:
                        print(f"  • {model_name}")
                    
                    # Test prediction
                    dummy_audio = np.zeros(1280, dtype=np.float32)
                    predictions = oww.predict(dummy_audio)
                    print(f"✅ Predictions working: {type(predictions)}")
                    
                    return oww, models
                else:
                    print(f"⚠️ No models loaded for {name}")
                    
            except Exception as e:
                print(f"❌ {name} failed: {e}")
                continue
        
        print("❌ All initialization approaches failed")
        return None, {}
        
    except Exception as e:
        print(f"❌ Error testing openWakeWord: {e}")
        import traceback
        traceback.print_exc()
        return None, {}

def download_onnx_models():
    """Try to download ONNX models for openWakeWord"""
    print("\n📥 Attempting to download ONNX models...")
    
    try:
        # Check if we can manually download models
        import requests
        
        # Common openWakeWord model URLs (these are examples - actual URLs may differ)
        model_urls = [
            "https://github.com/dscripka/openWakeWord/releases/download/v0.1.1/alexa_v0.1.onnx",
            "https://github.com/dscripka/openWakeWord/releases/download/v0.1.1/hey_mycroft_v0.1.onnx",
        ]
        
        models_dir = "openwakeword_models"
        os.makedirs(models_dir, exist_ok=True)
        
        downloaded_models = []
        for url in model_urls:
            try:
                model_name = url.split('/')[-1]
                model_path = os.path.join(models_dir, model_name)
                
                if not os.path.exists(model_path):
                    print(f"📥 Downloading {model_name}...")
                    response = requests.get(url)
                    if response.status_code == 200:
                        with open(model_path, 'wb') as f:
                            f.write(response.content)
                        print(f"✅ Downloaded {model_name}")
                        downloaded_models.append(model_path)
                    else:
                        print(f"⚠️ Failed to download {model_name} (HTTP {response.status_code})")
                else:
                    print(f"✅ {model_name} already exists")
                    downloaded_models.append(model_path)
                    
            except Exception as e:
                print(f"❌ Error downloading model from {url}: {e}")
        
        return downloaded_models
        
    except Exception as e:
        print(f"❌ Error downloading models: {e}")
        return []

def test_simple_approach():
    """Test a simpler approach to see what's available"""
    print("\n🔧 Testing simple openWakeWord approach...")
    
    try:
        # Just try to see what happens with basic initialization
        print("Creating model instance...")
        
        # Try with force_onnx flag if available
        try:
            oww = Model(inference_framework='onnx')
            print("✅ ONNX model initialized")
        except:
            try:
                oww = Model()
                print("✅ Default model initialized")
            except Exception as e:
                print(f"❌ Model initialization failed: {e}")
                return False
        
        # Check what we got
        print(f"Model object: {type(oww)}")
        print(f"Has models attribute: {hasattr(oww, 'models')}")
        
        if hasattr(oww, 'models'):
            print(f"Models: {oww.models}")
        
        return True
        
    except Exception as e:
        print(f"❌ Simple approach failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_potential_aiden_models():
    """Check which models might work for Aiden wake word"""
    print("\n🎯 Analyzing models for 'Aiden' compatibility...")
    
    try:
        oww = Model()
        models = oww.models
        
        # Keywords that might be suitable for Aiden
        aiden_keywords = [
            "hey", "alexa", "computer", "mycroft", "jarvis", 
            "assistant", "voice", "listen", "wake", "start"
        ]
        
        potential_models = []
        for model_name in models:
            model_lower = model_name.lower()
            for keyword in aiden_keywords:
                if keyword in model_lower:
                    potential_models.append(model_name)
                    break
        
        if potential_models:
            print(f"🎯 Potential models for wake word detection:")
            for model in potential_models:
                print(f"  • {model}")
        else:
            print("ℹ️ No obvious matches found - we can use any model as a general wake word")
            print("📝 Recommendation: Use the most sensitive model and retrain or use all models")
            
        return potential_models
        
    except Exception as e:
        print(f"❌ Error analyzing models: {e}")
        return []

def main():
    """Main test function"""
    print("🧪 openWakeWord Windows Compatibility Test")
    print("=" * 50)
    
    # Try simple approach first
    if test_simple_approach():
        print("\n✅ Basic functionality works!")
    
    # Try specific model loading
    oww, models = test_openwakeword_with_specific_models()
    
    if models:
        print(f"\n🎯 SUCCESS! Found {len(models)} working models")
        print("💡 We can use these for wake word detection!")
    else:
        print(f"\n⚠️ No models loaded, but openWakeWord might still work")
        print("💡 We might need to:")
        print("  1. Download specific ONNX models manually")
        print("  2. Use a different wake word library")
        print("  3. Train our own 'Aiden' model")
    
    print("\n🏁 Test completed!")

if __name__ == "__main__":
    main() 