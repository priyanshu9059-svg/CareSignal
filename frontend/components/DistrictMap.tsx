'use client';
import {useEffect,useRef} from 'react';
import 'leaflet/dist/leaflet.css';
export default function DistrictMap({districts}:{districts:any[]}) {
 const ref=useRef<HTMLDivElement>(null);
 useEffect(()=>{let map:import('leaflet').Map|undefined;let gone=false;
 import('leaflet').then(L=>{if(gone||!ref.current)return;map=L.map(ref.current).setView([23,77],5);
 L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(map);
 districts.forEach(d=>{const text=document.createElement('span');text.textContent=`${d.name}: ${d.count} synthetic cases; ${d.high} high/critical`;
 L.circleMarker([d.lat,d.lng],{radius:8+d.high,color:'#80533a',fillColor:'#cb9163',fillOpacity:.65}).addTo(map!).bindPopup(text);});});
 return()=>{gone=true;map?.remove();};},[districts]);
 return <div ref={ref} className="map" aria-label="Synthetic district risk density map"/>;
}
