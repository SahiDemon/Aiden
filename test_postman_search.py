#!/usr/bin/env python3
"""
Test script to search for Postman and similar apps
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.app_manager import AppManager

def search_postman():
    """Search for Postman and related apps"""
    print("=== Searching for Postman and API tools ===")
    
    app_manager = AppManager()
    all_apps = app_manager.get_installed_apps()
    
    # Search for apps containing "post", "api", "rest", "http"
    search_terms = ["post", "api", "rest", "http", "insomnia", "thunder"]
    
    print(f"Total apps: {len(all_apps)}")
    
    for term in search_terms:
        print(f"\n🔍 Apps containing '{term}':")
        matches = [app for app in all_apps if term.lower() in app['name'].lower()]
        
        if matches:
            for app in matches:
                print(f"   - {app['name']} (executable: {app['executable']})")
        else:
            print(f"   No apps found containing '{term}'")
    
    # Also search using the search function
    print(f"\n🔍 Search results for 'postman':")
    results = app_manager.search_apps("postman", limit=10)
    if results:
        for app in results:
            print(f"   - {app['name']} (executable: {app['executable']})")
    else:
        print("   No search results for 'postman'")
    
    # Show some development tools
    print(f"\n🔍 Development tools found:")
    dev_apps = [app for app in all_apps if any(term in app['name'].lower() for term in ['code', 'studio', 'git', 'node', 'python', 'java', 'docker'])]
    for app in dev_apps[:10]:
        print(f"   - {app['name']}")

if __name__ == "__main__":
    search_postman() 