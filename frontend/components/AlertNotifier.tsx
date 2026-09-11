'use client';
import {useEffect,useRef} from 'react';

/** Plays a short beep and optional browser notification when unread alerts rise. */
export default function AlertNotifier({unread,latestTitle}:{unread:number;latestTitle?:string}){
 const prev=useRef<number|null>(null);
 useEffect(()=>{
  if(typeof window==='undefined') return;
  if('Notification' in window && Notification.permission==='default'){
   Notification.requestPermission().catch(()=>{});
  }
 },[]);
 useEffect(()=>{
  if(prev.current===null){prev.current=unread;return;}
  if(unread>prev.current){
   try{
    const ctx=new (window.AudioContext||(window as any).webkitAudioContext)();
    const osc=ctx.createOscillator(); const gain=ctx.createGain();
    osc.type='sine'; osc.frequency.value=880;
    gain.gain.value=0.05; osc.connect(gain); gain.connect(ctx.destination);
    osc.start(); gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime+0.35);
    osc.stop(ctx.currentTime+0.4);
    setTimeout(()=>ctx.close().catch(()=>{}),500);
   }catch{/* audio optional */}
   if('Notification' in window && Notification.permission==='granted'){
    try{new Notification('CareSignal alert',{body:latestTitle||'New wellbeing check-in or risk alert needs review',tag:'caresignal-alert'});}catch{/* ignore */}
   }
  }
  prev.current=unread;
 },[unread,latestTitle]);
 return null;
}
