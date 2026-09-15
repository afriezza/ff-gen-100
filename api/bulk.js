// api/bulk.js - 115x paralel dispatcher
export default async function handler(req,res){
  res.setHeader("Access-Control-Allow-Origin","*");
  const q=req.query||{};
  const name=(q.name||"Sam").slice(0,20);
  const total=Math.min(parseInt(q.count||"115")||115,115);
  const region=(q.region||"ID").toUpperCase();
  const base="https://"+req.headers.host;
  const jobs=[];
  for(let i=1;i<=total;i++){
    const url=base+"/api/g"+i+"?name="+encodeURIComponent(name)+"&count=1&region="+region+"&detect_rare=true";
    jobs.push(fetch(url).then(r=>r.json()).catch(()=>({accounts:[]})));
  }
  const all=await Promise.all(jobs);
  const accounts=all.flatMap(x=>x.accounts||[]).slice(0,total);
  res.status(200).json({success:true,total_requested:total,total_created:accounts.length,rare_count:accounts.filter(a=>a.rare?.length).length,mode:"115x",accounts});
}
