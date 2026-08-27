import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import puppeteer from 'puppeteer-core'
const BASE='https://192.168.66.224:8443'
const SID = readFileSync(process.env.SIDFILE,'utf8').trim()
const spki = execSync(`openssl x509 -in /opt/openterminalapps/deploy/certs/ota.crt -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64`,{shell:'/bin/bash'}).toString().trim()
const b = await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:'new',
  args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage',`--ignore-certificate-errors-spki-list=${spki}`],
  defaultViewport:{width:1280,height:760}})
const p = await b.newPage()
await p.goto(BASE,{waitUntil:'networkidle2'})
await p.type('input[autocomplete="username"]','bmetallica')
await p.type('input[autocomplete="current-password"]','OtaStart2026!xyz')
await Promise.all([p.click('button.btn--primary'),p.waitForSelector('.rail')])

for (const [d,name] of [[1,'vscode-im-arbeitsplatz'],[2,'terminal'],[3,'dateien']]) {
  const url = d===1
    ? `${BASE}/s/${SID}/?path=s/${SID}/websockify`
    : `${BASE}/s/${SID}/a/${d}/?path=s/${SID}/a/${d}/websockify`
  await p.goto(url,{waitUntil:'domcontentloaded'})
  let st=null
  for (let i=0;i<24;i++){
    await new Promise(r=>setTimeout(r,1200))
    st = await p.evaluate(()=>({cls:document.documentElement.className, canvas:!!document.querySelector('canvas')}))
    if (st.cls.includes('noVNC_connected')) break
  }
  console.log(`  Display :${d} (${name}) -> ${st?.cls?.includes('noVNC_connected')?'verbunden':'NICHT verbunden ('+st?.cls+')'}, Canvas: ${st?.canvas}`)
  await new Promise(r=>setTimeout(r,3000))
  await p.screenshot({path:`${process.env.OUT}/app-${name}.png`})
}
await b.close()
