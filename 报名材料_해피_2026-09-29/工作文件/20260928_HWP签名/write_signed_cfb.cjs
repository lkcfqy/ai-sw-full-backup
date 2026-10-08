const fs=require('fs'),zlib=require('zlib'),assert=require('assert');
const CFB=require('../20260928_原生HWP填写/vendor/node_modules/cfb');
const [src,bodyPath,docInfoPath,jpgPath,dst]=process.argv.slice(2);
const original=CFB.read(src,{type:'file'}), cfb=CFB.utils.cfb_new();
const body=fs.readFileSync(bodyPath),di=fs.readFileSync(docInfoPath),jpg=fs.readFileSync(jpgPath);
for(let i=0;i<original.FileIndex.length;i++){
 const e=original.FileIndex[i],p=original.FullPaths[i];if(e.type!==2)continue;
 let data=Buffer.from(e.content);
 if(p.endsWith('/BodyText/Section0'))data=zlib.deflateRawSync(body);
 else if(p.endsWith('/DocInfo'))data=zlib.deflateRawSync(di);
 else if(p.endsWith('/PrvText'))data=Buffer.from('해피 — 참가자가 제공한 서명 이미지와 동의 선택을 반영한 문서\r\n본문을 열어 확인하십시오.\r\n','utf16le');
 CFB.utils.cfb_add(cfb,p,data);
}
CFB.utils.cfb_add(cfb,'Root Entry/BinData/BIN0001.jpg',jpg);
CFB.utils.cfb_gc(cfb);CFB.write(cfb,{type:'file',filename:dst});
const result=CFB.read(dst,{type:'file'});
assert.deepStrictEqual(Buffer.from(CFB.find(result,'/BinData/BIN0001.jpg').content),jpg);
assert.deepStrictEqual(zlib.inflateRawSync(CFB.find(result,'/DocInfo').content),di);
assert.deepStrictEqual(zlib.inflateRawSync(CFB.find(result,'/BodyText/Section0').content),body);
