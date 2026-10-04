# Aiden dashboard

The React 18 dashboard displays conversation state, system context, timers, settings, and ESP32 controls. It uses Create React App, Tailwind utilities, and component libraries.

## Develop

Start the Python backend separately, then:

```powershell
cd dashboard
npm ci
npm run dev
```

`dev` and `start` both run the React development server. Requests are proxied to `http://localhost:5000`; use the URL printed by the dev server. Node.js 22.12+ is the documented repository baseline.

## Verify and build

```powershell
$env:CI = 'true'
npm run test -- --watchAll=false
npm run build
```

The Python backend serves `build/` for normal use at [localhost:5000](http://localhost:5000). Generated assets and `node_modules` are ignored. Keep `package-lock.json` committed and use `npm ci` to reproduce dependencies.

After dashboard changes, manually verify wake-word status, system context, timers/cancel actions, and ESP32 widgets with your configured hardware. Preserve the [design principles](../docs/design.md). Automated component coverage does not replace these live checks.
