#!/usr/bin/env python3
"""
Aiden Dashboard Startup Script
Launches the dashboard backend server and optionally the main Aiden system
"""
import os
import sys
import subprocess
import threading
import time
import argparse
from pathlib import Path

def print_banner():
    """Print startup banner"""
    banner = """
    ╔══════════════════════════════════════╗
    ║        🤖 Aiden AI Dashboard        ║
    ║                                      ║
    ║     Modern Voice Assistant UI        ║
    ║                                      ║
    ╚══════════════════════════════════════╝
    """
    print(banner)

def check_dependencies(backend_only=False):
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    try:
        import flask
        import flask_cors
        import flask_socketio
        print("✅ Flask dependencies found")
    except ImportError as e:
        print(f"❌ Flask dependencies missing: {e}")
        print("Run: pip install -r requirements.txt")
        return False
    
    if not backend_only:
        # Check if dashboard frontend exists
        dashboard_path = Path("dashboard")
        if not dashboard_path.exists():
            print("❌ Dashboard frontend not found at ./dashboard/")
            return False
        
        package_json = dashboard_path / "package.json"
        if not package_json.exists():
            print("❌ Dashboard package.json not found")
            return False
        
        print("✅ Dashboard frontend found")
    else:
        print("⏭️  Skipping frontend checks (backend-only mode)")
    
    return True

def build_frontend():
    """Build the React frontend"""
    print("🔨 Building dashboard frontend...")
    
    dashboard_path = Path("dashboard")
    
    # Determine npm command based on OS
    npm_cmd = "npm.cmd" if os.name == 'nt' else "npm"
    
    # Check if npm is available
    try:
        result = subprocess.run([npm_cmd, "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ npm not found. Please install Node.js from https://nodejs.org/")
            return False
    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js from https://nodejs.org/")
        print("   After installation, restart your terminal and try again.")
        return False
    
    # Check if node_modules exists
    node_modules = dashboard_path / "node_modules"
    if not node_modules.exists():
        print("📦 Installing npm dependencies...")
        try:
            result = subprocess.run(
                [npm_cmd, "install"], 
                cwd=dashboard_path,
                capture_output=True,
                text=True,
                shell=True if os.name == 'nt' else False
            )
            
            if result.returncode != 0:
                print(f"❌ npm install failed: {result.stderr}")
                print(f"   stdout: {result.stdout}")
                return False
            print("✅ npm dependencies installed")
        except Exception as e:
            print(f"❌ Error running npm install: {e}")
            return False
    
    # Build the React app
    print("🔨 Building React app...")
    try:
        result = subprocess.run(
            [npm_cmd, "run", "build"], 
            cwd=dashboard_path,
            capture_output=True,
            text=True,
            shell=True if os.name == 'nt' else False
        )
        
        if result.returncode != 0:
            print(f"❌ Build failed: {result.stderr}")
            print(f"   stdout: {result.stdout}")
            return False
        
        print("✅ Dashboard frontend built successfully")
        return True
    except Exception as e:
        print(f"❌ Error running npm build: {e}")
        return False

def start_dashboard_backend():
    """Start the dashboard backend server"""
    print("🚀 Starting dashboard backend...")
    
    try:
        # Import and run the dashboard backend
        from src.dashboard_backend import AidenDashboardBackend
        
        backend = AidenDashboardBackend()
        print("✅ Dashboard backend initialized")
        print("🌐 Dashboard will be available at: http://localhost:5000")
        print("📱 Mobile access: http://YOUR_IP:5000")
        print("\n💡 Controls:")
        print("   - Use * key for voice activation")
        print("   - Type messages in the dashboard")
        print("   - Access settings via the gear icon")
        print("   - Control fan via the ESP32 section")
        print("\n⚡ Press Ctrl+C to stop the dashboard")
        
        # Run the backend (this will block)
        backend.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("\n🛑 Dashboard stopped by user")
    except Exception as e:
        print(f"❌ Error starting dashboard: {e}")
        import traceback
        traceback.print_exc()

def start_aiden_system():
    """Start the main Aiden system in a separate thread"""
    print("🤖 Starting main Aiden system...")
    
    try:
        from src.main import main as aiden_main
        aiden_main()
    except Exception as e:
        print(f"❌ Error starting Aiden system: {e}")

def main():
    """Main startup function"""
    parser = argparse.ArgumentParser(description='Start Aiden AI Dashboard')
    parser.add_argument('--dashboard-only', action='store_true', 
                       help='Start only the dashboard, not the main Aiden system')
    parser.add_argument('--skip-build', action='store_true',
                       help='Skip building the frontend (use existing build)')
    parser.add_argument('--backend-only', action='store_true',
                       help='Start only the backend API (no frontend)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port for the dashboard server (default: 5000)')
    
    args = parser.parse_args()
    
    print_banner()
    
    # Check dependencies
    if not check_dependencies(backend_only=args.backend_only):
        print("💔 Dependency check failed. Please fix the issues above.")
        sys.exit(1)
    
    # Build frontend if needed
    if not args.skip_build and not args.backend_only:
        print("🔍 Checking for Node.js...")
        if not build_frontend():
            print("💡 Frontend build failed. You have several options:")
            print("   1. Install Node.js from https://nodejs.org/ and try again")
            print("   2. Run with --backend-only to test the API")
            print("   3. Run with --skip-build if you have a working build")
            
            choice = input("\n❓ Continue with backend-only mode? (y/n): ").lower().strip()
            if choice in ['y', 'yes']:
                print("🎯 Continuing in backend-only mode...")
                args.backend_only = True
            else:
                print("💔 Exiting. Please install Node.js or use --backend-only flag.")
                sys.exit(1)
    elif args.skip_build:
        print("⏭️  Skipping frontend build")
    elif args.backend_only:
        print("🔧 Running in backend-only mode (API testing)")
    
    # Start the main Aiden system in background if requested
    if not args.dashboard_only and not args.backend_only:
        print("🎯 Starting in full mode (Dashboard + Main System)")
        aiden_thread = threading.Thread(target=start_aiden_system, daemon=True)
        aiden_thread.start()
        time.sleep(2)  # Give Aiden time to start
    elif args.dashboard_only:
        print("🎯 Starting in dashboard-only mode")
    else:
        print("🎯 Starting in backend-only mode (API only)")
    
    # Start dashboard backend (this will block)
    start_dashboard_backend()

if __name__ == '__main__':
    main()