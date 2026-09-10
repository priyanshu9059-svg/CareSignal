import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'CareSignal | Wellbeing & Support',description:'SIH 26094 — AI-assisted wellbeing monitoring with human-led support.',manifest:'/manifest.webmanifest'};
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }
