'use client';
import {useRef,useState,useEffect} from 'react';
import {Mic,Square} from 'lucide-react';
import {api} from '../lib/api';
export default function VoiceInput({caseId,language,t,onReady,onTranscript}:{caseId:string;language:string;t:any;onReady:(id:string)=>void;onTranscript:(text:string)=>void}) {
 const [recording,setRecording]=useState(false),[message,setMessage]=useState('');
 const stream=useRef<MediaStream|null>(null),context=useRef<AudioContext|null>(null),frames=useRef<Float32Array[]>([]),processor=useRef<ScriptProcessorNode|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null),recognition=useRef<any>(null),transcript=useRef('');
 async function closeAudio(){const active=context.current;context.current=null;if(active&&active.state!=='closed')await active.close();}
 useEffect(()=>()=>{stream.current?.getTracks().forEach(t=>t.stop());void closeAudio().catch(()=>{});recognition.current?.stop();if(timer.current)clearTimeout(timer.current);},[]);
 async function start(){try{
  stream.current=await navigator.mediaDevices.getUserMedia({audio:true});context.current=new AudioContext({sampleRate:16000});frames.current=[];transcript.current='';
  const source=context.current.createMediaStreamSource(stream.current);processor.current=context.current.createScriptProcessor(4096,1,1);
  processor.current.onaudioprocess=e=>frames.current.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  source.connect(processor.current);processor.current.connect(context.current.destination);
  const SR=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
  if(SR){const r=new SR();recognition.current=r;r.lang=language==='en'?'en-IN':'hi-IN';r.continuous=true;r.onresult=(e:any)=>{transcript.current=Array.from(e.results).map((v:any)=>v[0].transcript).join(' ');onTranscript(transcript.current);};r.onerror=()=>setMessage('Browser transcription unavailable. Server ASR may still help after you stop.');r.start();}
  else setMessage('Browser transcription unavailable. Server ASR may still help after you stop.');
  setRecording(true);timer.current=setTimeout(stop,90000);
 }catch{setMessage('Microphone unavailable. You can type your response.');stream.current?.getTracks().forEach(t=>t.stop());await closeAudio().catch(()=>{});}}
 async function stop(){
  if(timer.current)clearTimeout(timer.current);recognition.current?.stop();processor.current?.disconnect();stream.current?.getTracks().forEach(t=>t.stop());setRecording(false);
  const rate=context.current?.sampleRate||16000;await closeAudio();
  const length=frames.current.reduce((n,f)=>n+f.length,0);const buffer=new ArrayBuffer(44+length*2);const view=new DataView(buffer);
  const word=(offset:number,value:string)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
  word(0,'RIFF');view.setUint32(4,36+length*2,true);word(8,'WAVE');word(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);word(36,'data');view.setUint32(40,length*2,true);
  let offset=44;frames.current.forEach(f=>f.forEach(v=>{view.setInt16(offset,Math.max(-1,Math.min(1,v))*32767,true);offset+=2;}));
  const blob=new Blob([buffer],{type:'audio/wav'});
  if(!transcript.current.trim()){
   try{
    setMessage('Trying server transcription…');
    const asrForm=new FormData();asrForm.append('file',blob,'checkin.wav');asrForm.append('language',language);
    const asr=await api('/ai/transcribe',{method:'POST',body:asrForm});
    if(asr.ok&&asr.transcript){transcript.current=asr.transcript;onTranscript(asr.transcript);setMessage(asr.message||'Server transcript ready — please review.');}
    else setMessage(asr.message||'No server transcript. Please type the transcript.');
   }catch{setMessage('Server transcription unavailable. Please type the transcript.');}
  }
  const form=new FormData();form.append('file',blob,'checkin.wav');form.append('case_id',caseId);form.append('transcript',transcript.current);
  try {setMessage(m=>m.includes('transcript')?m+' Processing acoustic features…':'Processing recording…');const result=await api('/ai/analyze-voice',{method:'POST',body:form});onReady(result.voice_session_id);setMessage(`Recording processed (${result.duration}s). ${result.baseline_note}`);}
  catch(e){setMessage((e as Error).message+'. Your text can still be submitted.');}
 }
 return <div className="voice-box"><p>{t.voiceNote}</p><button type="button" className={recording?'danger':'secondary'} onClick={recording?stop:start}>{recording?<Square size={16}/>:<Mic size={16}/>} {recording?t.stop:t.record}</button><p role="status" className="muted">{message}</p></div>;
}
