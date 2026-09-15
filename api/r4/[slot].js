import h from "../../gen.js";
export default function handler(req,res){
  const slot=(req.query&&req.query.slot)||"1";
  req.query={...(req.query||{}),slot};
  res.setHeader("X-Api-Group","r4");
  return h(req,res);
}
