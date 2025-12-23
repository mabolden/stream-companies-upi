const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let backendProcess;

function waitForFlask(url, maxAttempts = 20, delay = 300) {
  return new Promise((resolve, reject) => {
    const attempt = (count) => {
      if (count === 0) return reject(new Error('Flask never started'));
      http.get(url, () => resolve()).on('error', () =>
        setTimeout(() => attempt(count - 1), delay)
      );
    };
    attempt(maxAttempts);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    icon: path.join(__dirname, 'icon.ico'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  win.loadURL('http://127.0.0.1:5000/');

  return win;
}

app.whenReady().then(async () => {
  const exePath = path.join(process.resourcesPath, 'backend', 'UPI.exe');
  backendProcess = spawn(exePath, [], { shell: true });

  backendProcess.stdout.on('data', (data) => {
    console.log(`Flask: ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`Flask error: ${data}`);
  });

  backendProcess.on('exit', (code, signal) => {
    console.log(`Backend exited with code ${code}, signal ${signal}`);
  });

  try {
    await waitForFlask('http://127.0.0.1:5000');
    createWindow();
  } catch (err) {
    console.error('Backend did not respond in time:', err);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    console.log('Killing backend process...');
    backendProcess.kill('SIGTERM'); // better to specify signal
    backendProcess = null;
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (backendProcess) {
    console.log('Cleaning up backend process before quit...');
    backendProcess.kill('SIGTERM');
  }
});
