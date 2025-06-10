# 📦 Node.js Installation Guide

To use the full Aiden Dashboard with the web interface, you need Node.js installed.

## 🪟 Windows Installation

### Option 1: Official Installer (Recommended)
1. **Visit**: https://nodejs.org/
2. **Download**: The LTS version (recommended for most users)
3. **Run**: The downloaded `.msi` installer
4. **Follow**: The installation wizard (accept defaults)
5. **Restart**: Your terminal/PowerShell after installation

### Option 2: Using Chocolatey (if you have it)
```powershell
choco install nodejs
```

### Option 3: Using Winget (Windows 10/11)
```powershell
winget install OpenJS.NodeJS
```

## ✅ Verify Installation

After installation, open a **new** terminal/PowerShell and run:
```bash
node --version
npm --version
```

You should see version numbers like:
```
v18.17.0
9.6.7
```

## 🚀 Test the Dashboard

Once Node.js is installed:
```bash
python start_dashboard.py
```

This will automatically install the React dependencies and build the dashboard!

## 🆘 Troubleshooting

### "npm not found" error
- **Restart** your terminal after installation
- **Add to PATH**: Make sure Node.js is in your system PATH
- **Reinstall**: Try reinstalling Node.js with "Add to PATH" checked

### Permission errors
- **Run as admin**: Try running the terminal as administrator
- **Check antivirus**: Some antivirus software blocks npm

### Alternative: Backend-Only Mode
If you can't install Node.js right now, you can still test the backend:
```bash
python start_dashboard.py --backend-only
```

Then use the API test script:
```bash
python test_dashboard_api.py
```

## 🎯 Next Steps

Once Node.js is working:
1. The dashboard will build automatically
2. Open http://localhost:5000 in your browser
3. Enjoy the modern Aiden interface!

---

**Need help?** Check the main DASHBOARD_README.md for more troubleshooting tips. 