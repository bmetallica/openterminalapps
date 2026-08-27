import { execSync } from 'node:child_process'
import puppeteer from 'puppeteer-core'
const BASE='https://192.168.66.224:8443'
const spki = execSync(`openssl x509 -in /opt/openterminalapps/deploy/certs/ota.crt -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64`,{shell:'/bin/bash'}).toString().trim()
const b = await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:'new',
  args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage',`--ignore-certificate-errors-spki-list=${spki}`],
  defaultViewport:{width:1440,height:900}})
const p = await b.newPage()
const ws=[]
p.on('console', m => { const t=m.text(); if (/websocket|websockify|connect/i.test(t)) ws.push(`${m.type()}: ${t}`) })
p.on('pageerror', e => ws.push('pageerror: '+e.message))
await p.goto(BASE,{waitUntil:'networkidle2'})
await p.type('input[autocomplete="username"]','bmetallica')
await p.type('input[autocomplete="current-password"]','OtaStart2026!xyz')
await Promise.all([p.click('button.btn--primary'),p.waitForSelector('.rail')])
await p.waitForSelector('.bay,.tiles',{timeout:20000})
if (await p.$('.bay')) await p.click('.bay .btn--primary'); else await p.click('.tile')
await p.waitForSelector('.viewer__frame',{timeout:120000})
await new Promise(r=>setTimeout(r,12000))
console.log('--- Meldungen ---'); ws.slice(0,8).forEach(m=>console.log('  '+m))
// Status im iframe auslesen
console.log('--- Zustand im Stream ---')
console.log(await p.evaluate(()=>{
  const d=document.querySelector('.viewer__frame')?.contentDocument
  if(!d) return {err:'kein Zugriff'}
  const status=d.querySelector('#noVNC_status')?.textContent
  const cls=d.documentElement.className
  return {status, cls, canvas: !!d.querySelector('canvas')}
}))
await p.screenshot({path:'/tmp/claude-0/-opt-openterminalapps/e2df8b47-a383-44ae-849e-1deb9db8ca0c/scratchpad/ws-check.png'})
await b.close()
