// api/bulk.js - 100x paralel dispatcher, ganti 1 API lemot jadi 100 tembakan
export default async function handler(req,res){
  res.setHeader("Access-Control-Allow-Origin","*");
  const q=req.query||{};
  const name=(q.name||"Sam").slice(0,20);
  const total=Math.min(parseInt(q.count||"100")||100,100);
  const region=(q.region||"ID").toUpperCase();
  const per=10, workers=Math.ceil(total/per);
  const base=`https://${req.headers.host}`;
  const jobs=[];
  for(let i=0;i<workers;i++){
    const url=`${base}/api/gen?name=${encodeURIComponent(name)}&count=${per}&region=${region}&detect_rare=true`;
    jobs.push(fetch(url).then(r=>r.json()).catch(()=>({accounts:[]})));
  }
  const all=await Promise.all(jobs);
  const accounts=all.flatMap(x=>x.accounts||[]).slice(0,total);
  res.status(200).json({success:true,total_requested:total,total_created:accounts.length,rare_count:accounts.filter(a=>a.rare?.length).length,accounts});
}
