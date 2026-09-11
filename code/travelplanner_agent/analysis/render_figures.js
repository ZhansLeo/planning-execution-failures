const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const dir = path.join(__dirname, 'figures');
(async () => {
  const files = fs.readdirSync(dir).filter(x => x.endsWith('.svg')).sort();
  for (const file of files) {
    await sharp(path.join(dir, file), { density: 216 })
      .resize(3200, 1800)
      .png({ compressionLevel: 9 })
      .toFile(path.join(dir, file.replace(/\.svg$/, '.png')));
  }
  process.stdout.write(JSON.stringify({ rendered: files.length }));
})().catch(err => { console.error(err); process.exit(1); });
