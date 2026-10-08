const fs=require('fs'),path=require('path'),zlib=require('zlib'),assert=require('assert');
const CFB=require('./vendor/node_modules/cfb');
const original=CFB.read(path.join(__dirname,'official-template.hwp'),{type:'file'});
const cfb=CFB.utils.cfb_new();
const body=fs.readFileSync(process.argv[2]);
for(let i=0;i<original.FileIndex.length;i++){
 const e=original.FileIndex[i],p=original.FullPaths[i];
 if(e.type!==2||p.endsWith('/PrvImage'))continue;
 let bytes=Buffer.from(e.content);
 if(p.endsWith('/BodyText/Section0'))bytes=zlib.deflateRawSync(body);
 if(p.endsWith('/PrvText'))bytes=Buffer.from('해피 — 공식 HWP 서식에 작성한 서명 전 문서\r\n본문을 열어 확인하십시오.\r\n','utf16le');
 CFB.utils.cfb_add(cfb,p,bytes);
}
CFB.utils.cfb_gc(cfb);
CFB.write(cfb,{type:'file',filename:process.argv[3]});
const reread=CFB.read(process.argv[3],{type:'file'});
assert.deepStrictEqual(zlib.inflateRawSync(CFB.find(reread,'/BodyText/Section0').content),body);
for(let i=0;i<original.FileIndex.length;i++){
 const e=original.FileIndex[i],p=original.FullPaths[i];
 if(e.type!==2||['/PrvImage','/PrvText','/BodyText/Section0'].some(x=>p.endsWith(x)))continue;
 assert.deepStrictEqual(Buffer.from(CFB.find(reread,p).content),Buffer.from(e.content),p);
}
console.log(JSON.stringify({file:path.basename(process.argv[3]),bytes:fs.statSync(process.argv[3]).size}));
