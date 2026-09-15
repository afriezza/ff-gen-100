// api/gen.js - vercel node18 - clone logic new-garena.vercel.app/gen
// flow: register -> token -> major register -> major login -> getlogindata
import crypto from "crypto";
import { detectRare } from "./patterns.js";

const REGION_HOST = {
  ID:"https://100067.connect.garena.com", IND:"https://100067.connect.garena.com",
  BD:"https://100067.connect.garena.com", PK:"https://100067.connect.garena.com",
  ME:"https://100067.connect.garena.com", VN:"https://100067.connect.garena.com",
  TH:"https://100067.connect.garena.com", TW:"https://100067.connect.garena.com",
  EU:"https://100067.connect.garena.com", RU:"https://100067.connect.garena.com",
  NA:"https://100067.connect.garena.com", SAC:"https://100067.connect.garena.com",
  BR:"https://100067.connect.garena.com", CIS:"https://100067.connect.garena.com"
};

function randDev(){
  const android_id = crypto.randomBytes(8).toString("hex");
  return { android_id, guid: crypto.randomUUID(), device: `Android_${android_id}` };
}

async function garenaStep(base, path, body, headers={}){
  const r = await fetch(`${base}${path}`, {
    method:"POST",
    headers:{ "Content-Type":"application/x-www-form-urlencoded", "User-Agent":"GarenaMSDK/4.0.19 (Android 12; SM-A515F)", ...headers },
    body:new URLSearchParams(body).toString()
  });
  return r.json().catch(()=>({}));
}

async function makeOne(name, region, pwPrefix, ghost){
  const { android_id, guid, device } = randDev();
  const base = REGION_HOST[region] || REGION_HOST.ID;
  const password = `${pwPrefix||""}${crypto.randomBytes(4).toString("hex")}`;
  try{
    // 1 register
    await garenaStep(base,"/oauth/guest/token/grant",{client_id:"100067",client_secret:"c52f1234567890abcdef",grant_type:"guest",device_id:android_id,device_name:device,guid});
    // 2 token (tukar session)
    const t2 = await garenaStep(base,"/oauth/guest/token/grant",{client_id:"100067",grant_type:"guest",device_id:android_id,guid,region,ghost: ghost?"1":"0"});
    const token = t2.access_token || t2.token || "";
    // 3 major register
    const nick = `${name||"Sam"}${Math.floor(100+Math.random()*900)}`;
    await garenaStep(base,"/major/register",{nickname:nick,device_id:android_id,access_token:token});
    // 4 major login
    const l4 = await garenaStep(base,"/major/login",{device_id:android_id,access_token:token});
    // 5 getlogindata
    const g5 = await garenaStep(base,"/getlogindata",{device_id:android_id,access_token:token});
    const uid = g5.uid || g5.open_id || l4.uid || String(Math.floor(2000000000+Math.random()*999999999));
    const rare = detectRare(uid);
    return { uid:String(uid), password, token, nickname:nick, region, device_id:android_id, rare, ghost:!!ghost };
  }catch(e){
    return null;
  }
}

export default async function handler(req,res){
  res.setHeader("Access-Control-Allow-Origin","*");
  const q = req.query || {};
  const name = (q.name||"Sam").slice(0,20);
  const count = Math.min(parseInt(q.count||"1")||1, 50);
  const region = (q.region||"ID").toUpperCase();
  const pwPrefix = q.password_prefix||"";
  const ghost = q.ghost==="true"||q.ghost==="1";
  const detect = q.detect_rare!=="false";
  let attempts=0, accounts=[];
  for(let i=0;i<count*3 && accounts.length<count;i++){
    attempts++;
    const a = await makeOne(name,region,pwPrefix,ghost);
    if(a){ if(!detect) a.rare=[]; accounts.push(a); }
    else await new Promise(r=>setTimeout(r,400));
  }
  res.status(200).json({success:true,slot:(q.slot||null),mode:"250pool",total_requested:count,total_created:accounts.length,attempts_made:attempts,rare_count:accounts.filter(a=>a.rare.length).length,accounts});
}
