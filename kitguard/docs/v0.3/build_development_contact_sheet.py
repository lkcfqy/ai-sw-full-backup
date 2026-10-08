"""Audit visualization of development views only; not an evaluation input image."""
from pathlib import Path
import json,hashlib
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]
base=ROOT/'datasets/manifests/v0.3/source_grouped_v2'
specs=json.loads((base/'screws_new_development_crop_specs_v1.json').read_text())['views']
manifest=json.loads((base/'screws_safe_crops_benchmark_v1.json').read_text())
cases={r['id']:r for r in manifest['cases'] if r['split']=='development'}
assert len(specs)==len(cases)==12
font_path='/System/Library/Fonts/Supplemental/Arial.ttf'
font=ImageFont.truetype(font_path,20); small=ImageFont.truetype(font_path,16); title=ImageFont.truetype(font_path,27)
w,h=1500,1830
canvas=Image.new('RGB',(w,h),'#f5f7f5'); draw=ImageDraw.Draw(canvas)
draw.text((24,18),'KitGuard v0.3 | 12 DEVELOPMENT views | NOT holdout',font=title,fill='#103d39')
draw.text((24,53),'MVTec Screws | CC BY-NC-SA 4.0 | author boxes in green | 16 px source boundary margin',font=small,fill='#41554d')
for i,r in enumerate(specs):
 c=cases[r['id']];col,row=i%3,i//3;x,y=24+col*494,90+row*430
 g=r['ground_truth'];name=Path(r['source_image']).name
 draw.text((x,y),f'{i+1:02d} {name}  screw={g["bolt"]} nut={g["nut"]}',font=font,fill='#103d39')
 with Image.open(ROOT/'datasets'/c['image']) as im:
  im.load();assert hashlib.sha256((ROOT/'datasets'/c['image']).read_bytes()).hexdigest()==c['sha256']
  view=im.copy();view.thumbnail((466,350));scale=view.width/r['width']
 canvas.paste(view,(x,y+33))
 dd=ImageDraw.Draw(canvas);left,top,_,_=r['crop_xyxy']
 for a in r['all_source_annotations']:
  if a['id'] not in r['included_annotation_ids']:continue
  x1,y1,x2,y2=a['conservative_aabb_xyxy'];dd.rectangle((x+(x1-left)*scale,y+33+(y1-top)*scale,x+(x2-left)*scale,y+33+(y2-top)*scale),outline='#33dd65',width=2)
 draw.text((x,y+390),f'Crop {r["width"]}x{r["height"]} | source group: development',font=small,fill='#41554d')
out=ROOT/'docs/v0.3/SCREWS_DEVELOPMENT_CONTACT_SHEET.png'
if out.exists():raise RuntimeError('Refuse to overwrite existing review sheet')
canvas.save(out)
print(out)
