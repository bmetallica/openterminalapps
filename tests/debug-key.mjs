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

console.log(await p.evaluate(() => {
  const f = document.querySelector('.viewer__frame')
  let doc=null, err=null
  try { doc = f.contentDocument } catch(e){ err=String(e) }
  return {
    sameOrigin: !!doc,
    err,
    innerTitle: doc?.title,
    activeTag: document.activeElement?.tagName,
    innerActive: doc?.activeElement?.tagName,
    frames: window.frames.length,
  }
}))

// Ereignis direkt im iframe auslösen und sehen, ob der Zuhörer greift
console.log('--- synthetisches Ereignis im iframe ---')
console.log(await p.evaluate(() => {
  const f = document.querySelector('.viewer__frame')
  const doc = f.contentDocument
  const before = !!document.querySelector('.viewer__bar')
  doc.dispatchEvent(new KeyboardEvent('keydown',{key:'A',ctrlKey:true,altKey:true,shiftKey:true,bubbles:true}))
  return { barBefore: before }
}))
await new Promise(r=>setTimeout(r,600))
console.log('  Leiste danach offen:', !!(await p.$('.viewer__bar')))

console.log('--- echte Tastatur über puppeteer ---')
await p.keyboard.down('Control'); await p.keyboard.down('Alt'); await p.keyboard.down('Shift')
await p.keyboard.press('KeyA')
await p.keyboard.up('Shift'); await p.keyboard.up('Alt'); await p.keyboard.up('Control')
await new Promise(r=>setTimeout(r,600))
console.log('  Leiste danach offen:', !!(await p.$('.viewer__bar')))
await b.close()
