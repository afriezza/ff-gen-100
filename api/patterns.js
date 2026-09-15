// api/patterns.js - 12 rare patterns, sama kayak new-garena
export const PATTERNS = [
  {name:"R4",pattern:"(\\d)\\1{3,}",score:3},
  {name:"R3",pattern:"(\\d)\\1\\1(\\d)\\2\\2",score:2},
  {name:"S5",pattern:"(12345|23456|34567|45678|56789)",score:4},
  {name:"S4",pattern:"(0123|1234|2345|3456|4567|5678|6789|9876|8765|7654|6543|5432|4321|3210)",score:3},
  {name:"P6",pattern:"^(\\d)(\\d)(\\d)\\3\\2\\1$",score:5},
  {name:"P4",pattern:"^(\\d)(\\d)\\2\\1$",score:3},
  {name:"SPH",pattern:"(69|420|1337|007)",score:4},
  {name:"SPM",pattern:"(100|200|300|400|500|666|777|888|999)",score:2},
  {name:"QD",pattern:"(1111|2222|3333|4444|5555|6666|7777|8888|9999|0000)",score:4},
  {name:"MH",pattern:"^(\\d{2,3})\\1$",score:3},
  {name:"MM",pattern:"(\\d{2})0\\1",score:2},
  {name:"GD",pattern:"1618|0618",score:3}
];
export function detectRare(uid){
  const s=String(uid); const hit=[];
  for(const p of PATTERNS){ try{ if(new RegExp(p.pattern).test(s)) hit.push(p.name); }catch{} }
  return hit;
}
export default function handler(req,res){
  res.setHeader("Access-Control-Allow-Origin","*");
  res.status(200).json({total_patterns:PATTERNS.length,patterns:PATTERNS});
}
