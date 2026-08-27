import { execSync } from 'node:child_process'
import puppeteer from 'puppeteer-core'
const BASE='https://192.168.66.224:8443'
const spki = execSync(`openssl x509 -in /opt/openterminalapps/deploy/certs/ota.crt -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64`,{shell:'/bin/bash'}).toString().trim()
const b = await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:'new',
  args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage',`--ignore-certificate-errors-spki-list=${spki}`],
  defaultViewport:{width:1440,height:900}})
await b.defaultBrowserContext().overridePermissions(BASE,['clipboard-read','clipboard-write'])
const p = await b.newPage()
await p.goto(BASE,{waitUntil:'networkidle2'})
// Direkt auf der Login-Seite prüfen — kein iframe im Spiel
console.log('Grundtest ohne iframe:')
console.log(' ', await p.evaluate(async () => {
  try {
    await navigator.clipboard.writeText('hallo-welt-123')
    const back = await navigator.clipboard.readText()
    return { ok: true, back, focused: document.hasFocus() }
  } catch (e) { return { ok:false, err:String(e), focused: document.hasFocus() } }
}))
await b.close()
