import puppeteer from 'puppeteer-core'
import { readFileSync } from 'node:fs'
const pw = readFileSync('/opt/openterminalapps/deploy/.env','utf8').match(/OTA_TEST_ADMIN_PW=(.*)/)[1].trim()
const url = readFileSync('/tmp/claude-0/-opt-openterminalapps/e2df8b47-a383-44ae-849e-1deb9db8ca0c/scratchpad/stream_url','utf8').trim()
const b = await puppeteer.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox','--ignore-certificate-errors']})
const pg = await b.newPage()
await pg.goto('https://192.168.66.224:8443/',{waitUntil:'networkidle2'})
await pg.type('input[autocomplete="username"]','bmetallica'); await pg.type('input[autocomplete="current-password"]',pw)
await Promise.all([pg.click('button.btn--primary'), pg.waitForSelector('.rail',{timeout:20000})])
const v = await b.newPage()
await v.goto('https://192.168.66.224:8443'+url,{waitUntil:'networkidle2'})
await new Promise(r=>setTimeout(r,6000))
const merkmale = () => v.evaluate(()=>({
  status: document.getElementById('noVNC_status')?.textContent?.trim(),
  statusKlassen: document.getElementById('noVNC_status')?.className,
  transitionKlassen: document.getElementById('noVNC_transition')?.className,
  sichtbar: [...document.querySelectorAll('[id^=noVNC_]')].filter(e=>{
      const s=getComputedStyle(e); return s.display!=='none' && /disconnect|status|transition/i.test(e.id)
    }).map(e=>e.id),
  klassenAmBody: document.documentElement.className,
}))
console.log('verbunden :', await merkmale())
// Jetzt die Verbindung von aussen kappen
