import { execSync } from 'node:child_process'
import puppeteer from 'puppeteer-core'
const BASE='https://192.168.66.224:8443'
const spki = execSync(`openssl x509 -in /opt/openterminalapps/deploy/certs/ota.crt -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64`,{shell:'/bin/bash'}).toString().trim()
const b = await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:'new',
  args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage',`--ignore-certificate-errors-spki-list=${spki}`],
  defaultViewport:{width:1440,height:900}})
const p = await b.newPage()
await p.goto(BASE,{waitUntil:'networkidle2'})
await p.type('input[autocomplete="username"]','bmetallica')
await p.type('input[autocomplete="current-password"]','OtaStart2026!xyz')
await Promise.all([p.click('button.btn--primary'),p.waitForSelector('.rail')])
await p.waitForSelector('.bay,.tiles',{timeout:20000})
if (await p.$('.bay')) await p.click('.bay .btn--primary'); else await p.click('.tile')
await p.waitForSelector('.viewer__frame',{timeout:120000})
await new Promise(r=>setTimeout(r,7000))

// Sonden an allen drei Stellen anbringen
await p.evaluate(() => {
  window.__probe = []
  const f = document.querySelector('.viewer__frame')
  const w = f.contentWindow, d = f.contentDocument
  window.addEventListener('keydown', e => window.__probe.push(`parent-win ${e.key} c${+e.ctrlKey}a${+e.altKey}s${+e.shiftKey}`), true)
  w.addEventListener('keydown', e => window.__probe.push(`iframe-win ${e.key} c${+e.ctrlKey}a${+e.altKey}s${+e.shiftKey}`), true)
  d.addEventListener('keydown', e => window.__probe.push(`iframe-doc ${e.key}`), true)
})

console.log('--- echte Tastatur (Strg+Alt+Shift+A) ---')
await p.keyboard.down('Control'); await p.keyboard.down('Alt'); await p.keyboard.down('Shift')
await p.keyboard.press('KeyA')
await p.keyboard.up('Shift'); await p.keyboard.up('Alt'); await p.keyboard.up('Control')
await new Promise(r=>setTimeout(r,700))
console.log('  Ereignisse:', await p.evaluate(()=>window.__probe))
console.log('  Leiste offen:', !!(await p.$('.viewer__bar')))

console.log('\n--- Klick ins iframe, dann erneut ---')
await p.evaluate(()=>{window.__probe=[]})
const box = await (await p.$('.viewer__frame')).boundingBox()
await p.mouse.click(box.x + box.width/2, box.y + box.height/2)
await new Promise(r=>setTimeout(r,400))
await p.keyboard.down('Control'); await p.keyboard.down('Alt'); await p.keyboard.down('Shift')
await p.keyboard.press('KeyA')
await p.keyboard.up('Shift'); await p.keyboard.up('Alt'); await p.keyboard.up('Control')
await new Promise(r=>setTimeout(r,700))
console.log('  Ereignisse:', await p.evaluate(()=>window.__probe))
console.log('  Leiste offen:', !!(await p.$('.viewer__bar')))
await b.close()
