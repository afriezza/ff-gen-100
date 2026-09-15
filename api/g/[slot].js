import h from "../gen.js";
export default function handler(req,res){
  const slot = (req.query && req.query.slot) || "1";
  req.query = { ...(req.query||{}), slot };
  return h(req,res);
}
