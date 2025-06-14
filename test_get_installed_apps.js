const { getInstalledApps, getWinInstalledApps } = require('get-installed-apps');

console.log('Testing get-installed-apps package...\n');

async function testGeneralMethod() {
    console.log('=== Testing General Method (getInstalledApps) ===');
    try {
        const apps = await getInstalledApps();
        console.log(`Found ${apps.length} installed applications\n`);
        
        // Show first 3 apps as examples
        console.log('First 3 applications:');
        apps.slice(0, 3).forEach((app, index) => {
            console.log(`${index + 1}. ${app.appName || app.DisplayName || 'Unknown Name'}`);
            console.log(`   Version: ${app.appVersion || app.DisplayVersion || 'Unknown'}`);
            console.log(`   Publisher: ${app.appPublisher || app.Publisher || 'Unknown'}`);
            console.log(`   Install Location: ${app.InstallLocation || 'Unknown'}`);
            console.log('');
        });
        
        // Look for some common applications
        console.log('Looking for common applications:');
        const commonApps = ['Postman', 'Firefox', 'Visual Studio', 'Code', 'Notepad'];
        commonApps.forEach(appName => {
            const found = apps.find(app => 
                (app.appName && app.appName.toLowerCase().includes(appName.toLowerCase())) ||
                (app.DisplayName && app.DisplayName.toLowerCase().includes(appName.toLowerCase()))
            );
            if (found) {
                console.log(`✓ Found: ${found.appName || found.DisplayName}`);
            } else {
                console.log(`✗ Not found: ${appName}`);
            }
        });
        
        console.log('\n=== Raw data sample (first app) ===');
        console.log(JSON.stringify(apps[0], null, 2));
        
    } catch (error) {
        console.error('Error with general method:', error.message);
    }
}

async function testWindowsMethod() {
    console.log('\n\n=== Testing Windows-Specific Method (getWinInstalledApps) ===');
    try {
        const apps = await getWinInstalledApps();
        console.log(`Found ${apps.length} installed applications (Windows method)\n`);
        
        // Show first 2 apps as examples
        console.log('First 2 applications (Windows method):');
        apps.slice(0, 2).forEach((app, index) => {
            console.log(`${index + 1}. ${app.appName || app.DisplayName || 'Unknown Name'}`);
            console.log(`   Version: ${app.appVersion || app.DisplayVersion || 'Unknown'}`);
            console.log(`   Publisher: ${app.appPublisher || app.Publisher || 'Unknown'}`);
            console.log('');
        });
        
    } catch (error) {
        console.error('Error with Windows method:', error.message);
    }
}

async function runTests() {
    try {
        await testGeneralMethod();
        await testWindowsMethod();
        console.log('\n=== Test Complete ===');
    } catch (error) {
        console.error('Test failed:', error);
    }
}

// Run the tests
runTests(); 