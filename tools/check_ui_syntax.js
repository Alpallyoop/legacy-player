// Syntax check for the single-file UI (launcher/ui/index.html).
//
//   node tools/check_ui_syntax.js            prints "ok <number of script blocks>", or "ERR <block> <message>" and exits 1
//
// The page's Content-Security-Policy forbids eval, so a syntax error in any <script> block only shows up when the app
// is opened. This compiles every block with new Function (it does not run it) so the mistake is caught before then.
// Run it after every edit to index.html.
const fs = require("fs");
const path = require("path");

const file = process.argv[2] || path.join(__dirname, "..", "launcher", "ui", "index.html");
const text = fs.readFileSync(file, "utf8");
const re = /<script[^>]*>([\s\S]*?)<\/script>/g;
let m, i = 0;
while ((m = re.exec(text))) {
  try {
    new Function(m[1]);
  } catch (e) {
    console.log("ERR", i, e.message);
    process.exit(1);
  }
  i++;
}
console.log("ok", i);
