"""Actual timed browser samples; retain model waits and disclose sampling/voice."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'tmp/scoring-video';OUT=ROOT/'output/competition-final-dev4'
FF=ROOT/'.tools/imageio-ffmpeg/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1'
FONT='/System/Library/Fonts/Supplemental/Arial Unicode.ttf'

def run(args,log):
 with (BUILD/(log+'.log')).open('w') as f:subprocess.run([str(x) for x in args],stdout=f,stderr=subprocess.STDOUT,check=True)

def stamp(value):
 return f'{int(value//3600)}:{int(value//60)%60:02}:{value%60:05.2f}'

def concat_samples(name,maximum=None,tail_hold=1):
 directory=ROOT/'test-results/scoring-v1/recording'/name
 frames=json.loads((directory/'frames.json').read_text())['frames'];zero=frames[0]['at'];items=[]
 duration=(frames[-1]['at']-zero)/1000+tail_hold
 if maximum is not None:duration=min(duration,maximum)
 for i,frame in enumerate(frames):
  start=(frame['at']-zero)/1000
  if start>=duration:break
  end=min((frames[i+1]['at']-zero)/1000 if i+1<len(frames) else duration,duration)
  # Hold the actual sampled screen between documented capture times, no interpolation.
  items.append(f"file '{directory/frame['path']}'\nduration {end-start:.6f}\n")
 last=items[-1].split('\n')[0];target=BUILD/(name+'.ffconcat');target.write_text('ffconcat version 1.0\n'+''.join(items)+last+'\n')
 return target,duration

def segment(source,duration,name):
 run([FF,'-hide_banner','-y','-f','concat','-safe','0','-i',source,'-vf','scale=1900:900:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:70:color=0xF4F7F3,fps=12,tpad=stop_mode=clone:stop_duration=4','-frames:v',str(math.ceil(duration*12)),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-an',BUILD/(name+'.mp4')],name)

def main():
 BUILD.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
 own,own_s=concat_samples('own-goal');all_,all_s=concat_samples('all-cases',tail_hold=3);segment(own,own_s,'own');segment(all_,all_s,'all')
 final=ROOT/'test-results/scoring-v1/final-tools-ko.jpg'
 run([FF,'-hide_banner','-y','-loop','1','-i',final,'-t','5','-vf','scale=1900:900:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:70:color=0xF4F7F3','-r','12','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-an',BUILD/'tools.mp4'],'tools')
 total=own_s+all_s+5;assert total<180,total
 join=BUILD/'join.ffconcat';join.write_text('ffconcat version 1.0\n'+''.join(f"file '{BUILD/(n+'.mp4')}'\n" for n in ['own','all','tools']))
 run([FF,'-hide_banner','-y','-f','concat','-safe','0','-i',join,'-c','copy',BUILD/'raw.mp4'],'join')
 captions=[(0,own_s,'01  현재 자료 + 내 BOM → 새 검증·차이 기록 / 실제 서버 실행20.213초'),(own_s,own_s+all_s,'02  공개3장 자율 목표 → 차이·불확실성·예정R2 / 실제137.071초'),(own_s+all_s,total,'03  저장된 도구 결과: R1 무효화 → 같은 사진 명시 재사용 → 새 R2 검사')]
 events='\n'.join(f'Dialogue: 0,{stamp(a)},{stamp(b)},Title,,0,0,0,,{t}' for a,b,t in captions)
 events+=f'\nDialogue: 0,0:00:00.00,{stamp(total)},Disclosure,,0,0,0,,실제 브라우저 시간 샘플 / 샘플 사이 정지화면 / 모델 대기 미압축 / 음성 합성 / 인간 검증0명'
 ass=BUILD/'captions.ass';ass.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Title,Arial Unicode MS,32,&H00353B17,&H0,&H00F3F7F4,&H00F3F7F4,-1,0,0,0,100,100,0,0,3,5,0,8,40,40,14,1\nStyle: Disclosure,Arial Unicode MS,25,&H00687963,&H0,&H00F3F7F4,&H00F3F7F4,0,0,0,0,100,100,0,0,3,5,0,2,40,40,25,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'+events+'\n')
 script='킷가드는 현재 사진과 주문 수량을 목표로 받아 기존 맥에서 검토합니다. 첫 자료는 나사류 두 개를 요구했고, 실제 관찰은 세 개여서 차이를 기록했습니다. 이 영상은 실제 브라우저 화면을 시간 간격대로 채집한 기록입니다. 샘플 사이에는 화면이 정지하며, 모델 대기 시간은 압축하지 않았습니다. 목소리는 합성 음성입니다. 이어서 공개 사진 세 장을 자율 검토하는 실제 실행을 보겠습니다. 작은 부품은 불확실성을 보존하고, 예정된 주문 변경 후 새로 추론합니다. 실제 사람의 시간 절감이나 실물 완료를 증명하는 시연은 아닙니다.'
 words=BUILD/'narration-ko.txt';words.write_text(script);voice=BUILD/'narration.aiff';run(['say','-v','Yuna','-r','185','-f',words,'-o',voice],'voice')
 output=OUT/'KitGuard_demo_ko.mp4'
 run([FF,'-hide_banner','-y','-i',BUILD/'raw.mp4','-i',voice,'-vf',f'ass={ass}','-af',f'apad=whole_dur={total:.6f}','-t',f'{total:.6f}','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',output],'final')
 run([FF,'-hide_banner','-v','error','-i',output,'-f','null','-'],'full-decode')
 for at in [0,21,45,100,total-2]:run([FF,'-hide_banner','-y','-ss',str(at),'-i',output,'-frames:v','1',BUILD/f'frame-{at:.1f}.png'],f'frame-{at:.1f}')
 meta={'version':'0.9.0.dev4','duration_requested_seconds':total,'own_goal_seconds':own_s,'all_raw_wall_seconds':all_s-2,'post_completion_hold_seconds':2,'server_mission_ms':137071,'human_validation_participants':0,'physical_completions':0,'new_accuracy_denominator':0,'method':'Timed actual browser samples, actual gaps held as still screens; no native continuous recording claim. Full own-goal and all-case timelines retained, final completed screen held2 extra seconds. All model waits retained. Final5sec tool-result still. Separate captions and local Yuna synthetic narration. Screenshots unretouched.',
 'input_frame_manifests':{n:hashlib.sha256((ROOT/'test-results/scoring-v1/recording'/n/'frames.json').read_bytes()).hexdigest() for n in ['own-goal','all-cases']},'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'full_decode':'passed','visual_qa':'pending'}
 (OUT/'video-build.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(output),'seconds':total},ensure_ascii=False))
if __name__=='__main__':main()
