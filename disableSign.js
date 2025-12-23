exports.default = async function (context) {
  const fs = require("fs");
  const path = require("path");

  const backendExe = path.join(context.appOutDir, "resources", "backend", "UPI.exe");
  if (fs.existsSync(backendExe)) {
    console.log("Skipping code signing for backend UPI.exe");
    // Do nothing — we're intentionally skipping code signing.
  }
};
