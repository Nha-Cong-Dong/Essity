import Link from "next/link";

import { Mascot } from "@/components/mascot";

import { fsrsCurve } from "./fsrs-curve";
import styles from "./landing.module.css";
import { LandingMotion } from "./landing-motion";

// LANDING-V61-PORT: the approved landing v6.1 (DESIGN-V5/versions/landing-v6.1.html). A server component: all
// structure and text is here, finished and readable without script; landing-motion.tsx only animates it.
// Colours and fonts: the mockup palette is local to .lp (see landing.module.css); the Mây mascot is the app component.

const CURVE = fsrsCurve();
const v = (o: Record<string, string | number>) => o as React.CSSProperties;

export function Landing() {
  return (
    <div className={styles.lp} data-landing="">
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
        <defs>
      <symbol id="d-do-thi" viewBox="0 0 48 48">
      <path d="M14.84 14.42C14.41 14.76 13.2 16.14 12.24 16.43C11.28 16.73 10 16.59 9.06 16.18C8.12 15.78 7.12 14.93 6.63 14.01C6.14 13.08 5.87 11.66 6.13 10.62C6.39 9.58 7.28 8.34 8.18 7.78C9.09 7.22 10.55 7.05 11.57 7.25C12.58 7.46 13.64 8.22 14.27 8.99C14.9 9.75 15.31 10.87 15.36 11.83C15.4 12.8 14.78 14.13 14.52 14.79C14.25 15.46 13.89 15.66 13.77 15.83" />
      <path d="M30.8 12.72C31.08 12.29 31.76 10.83 32.49 10.16C33.22 9.5 34.2 8.89 35.16 8.72C36.12 8.54 37.34 8.68 38.23 9.09C39.12 9.5 39.99 10.34 40.5 11.18C41 12.02 41.27 13.14 41.27 14.12C41.26 15.11 40.98 16.22 40.46 17.1C39.94 17.97 39.1 18.89 38.15 19.37C37.2 19.84 35.86 20.13 34.77 19.97C33.69 19.8 32.41 19.16 31.63 18.37C30.84 17.57 30.25 16.3 30.06 15.21C29.88 14.11 30.3 12.56 30.51 11.79C30.72 11.02 31.2 10.8 31.33 10.6" />
      <path d="M15.5 30.77C16.02 30.78 17.69 30.53 18.63 30.84C19.58 31.14 20.56 31.84 21.19 32.61C21.82 33.38 22.29 34.46 22.44 35.47C22.58 36.48 22.49 37.71 22.07 38.68C21.64 39.66 20.84 40.74 19.91 41.32C18.98 41.9 17.59 42.27 16.49 42.17C15.38 42.07 14.1 41.45 13.28 40.72C12.46 39.99 11.85 38.82 11.59 37.79C11.32 36.76 11.39 35.55 11.68 34.56C11.97 33.57 12.58 32.53 13.34 31.85C14.09 31.16 15.51 30.7 16.23 30.43C16.94 30.17 17.38 30.29 17.61 30.26" />
      <path d="M36.01 33.58C36.56 33.52 38.38 32.87 39.28 33.21C40.18 33.55 41.1 34.73 41.4 35.62C41.7 36.51 41.5 37.75 41.1 38.54C40.69 39.33 39.81 40.1 38.97 40.37C38.13 40.64 36.86 40.6 36.07 40.15C35.29 39.71 34.45 38.62 34.27 37.73C34.09 36.83 34.46 35.53 34.99 34.77C35.51 34.01 37.03 33.44 37.44 33.16C37.84 32.87 37.41 33.07 37.4 33.06" />
      <path d="M18.38 12.29Q23.03 12.74 27.63 13.61" />
      <path d="M12.71 19.19Q13.67 23.55 14.98 27.82" />
      <path d="M30.73 20.26Q26.6 24.7 22.83 29.45" />
      <path d="M36.47 22.3Q37.19 26.09 37.76 29.89" />
      <path d="M25.22 36.12Q28.28 36.42 31.32 36.85" />
      </symbol>
      <symbol id="d-kep-giay" viewBox="0 0 48 48">
      <path d="M15.81 28.71C16.19 28.09 17.45 26.07 18.1 25.02C18.74 23.98 19.18 23.35 19.69 22.45C20.2 21.55 20.7 20.55 21.15 19.62C21.61 18.69 21.94 17.86 22.42 16.85C22.89 15.85 23.56 14.44 24 13.59C24.45 12.74 24.6 12.2 25.06 11.73C25.52 11.26 26.08 11 26.79 10.77C27.5 10.54 28.48 10.3 29.32 10.36C30.17 10.43 31.11 10.7 31.85 11.18C32.58 11.66 33.34 12.45 33.73 13.25C34.11 14.05 34.19 15.23 34.15 15.97C34.11 16.72 34 16.77 33.5 17.72C32.99 18.68 31.8 20.59 31.13 21.71C30.46 22.83 30.02 23.49 29.49 24.43C28.95 25.38 28.41 26.41 27.91 27.37C27.4 28.33 27.01 29.18 26.46 30.21C25.91 31.24 25.16 32.63 24.61 33.55C24.06 34.46 23.7 35.17 23.16 35.68C22.62 36.19 22.09 36.32 21.39 36.61C20.7 36.89 19.82 37.25 19 37.38C18.18 37.52 17.31 37.57 16.47 37.44C15.64 37.31 14.73 37.05 13.99 36.61C13.24 36.16 12.49 35.5 11.99 34.77C11.5 34.03 11.14 33.09 11 32.21C10.85 31.33 11 30.24 11.12 29.48C11.25 28.73 11.38 28.54 11.75 27.68C12.12 26.82 12.82 25.39 13.32 24.3C13.82 23.21 14.22 22.24 14.76 21.16C15.29 20.07 15.9 18.89 16.52 17.78C17.14 16.67 17.85 15.54 18.5 14.51C19.15 13.49 19.76 12.63 20.41 11.61C21.05 10.59 21.89 9.17 22.36 8.41C22.83 7.64 22.76 7.57 23.24 7.03C23.72 6.5 24.49 5.69 25.24 5.21C25.99 4.73 26.89 4.34 27.76 4.16C28.64 3.98 29.6 3.99 30.48 4.12C31.35 4.26 32.22 4.58 33.01 4.96C33.8 5.34 34.55 5.84 35.22 6.41C35.9 6.99 36.55 7.65 37.05 8.41C37.55 9.16 38.01 10.05 38.23 10.95C38.45 11.85 38.52 12.9 38.39 13.81C38.26 14.72 37.93 15.45 37.46 16.43C37 17.41 36.22 18.59 35.6 19.7C34.98 20.81 34.35 21.95 33.75 23.08C33.16 24.21 32.62 25.4 32.04 26.49C31.46 27.57 30.57 29.08 30.25 29.59C29.93 30.09 30.15 29.53 30.12 29.52" />
      </symbol>
      <symbol id="d-the" viewBox="0 0 48 48">
      <path d="M9 14.82C9.68 14.8 11.77 14.72 13.1 14.71C14.43 14.7 15.61 14.78 16.98 14.77C18.35 14.76 19.86 14.66 21.31 14.64C22.76 14.61 24.28 14.58 25.67 14.63C27.06 14.69 28.46 14.84 29.64 14.97C30.83 15.1 31.69 15.3 32.8 15.41C33.91 15.51 35.63 15.18 36.3 15.61C36.97 16.05 36.65 16.87 36.83 18.01C37 19.16 37.25 21.25 37.34 22.49C37.44 23.73 37.37 24.44 37.38 25.45C37.39 26.46 37.36 27.54 37.39 28.55C37.42 29.56 37.56 30.28 37.58 31.52C37.6 32.77 37.66 34.76 37.52 36.03C37.38 37.31 37.54 38.64 36.76 39.16C35.98 39.67 34.02 39.15 32.84 39.13C31.66 39.11 30.87 39.03 29.69 39.03C28.52 39.03 27.16 39.12 25.79 39.16C24.42 39.19 22.93 39.26 21.5 39.24C20.07 39.22 18.58 39.12 17.21 39.05C15.85 38.98 14.49 38.84 13.31 38.8C12.14 38.76 11.34 38.81 10.18 38.83C9.03 38.85 7.14 39.39 6.38 38.92C5.61 38.46 5.77 37.26 5.61 36.03C5.44 34.79 5.41 32.76 5.39 31.51C5.36 30.26 5.47 29.54 5.47 28.52C5.47 27.51 5.42 26.43 5.41 25.41C5.4 24.4 5.31 23.68 5.39 22.44C5.47 21.2 5.49 19.07 5.91 17.98C6.32 16.89 7.36 16.29 7.87 15.88C8.39 15.46 8.81 15.56 9 15.5" />
      <path d="M11.85 15.01C11.75 14.4 11.01 12.45 11.26 11.35C11.51 10.25 12.06 8.92 13.37 8.42C14.68 7.93 17.55 8.41 19.14 8.39C20.72 8.36 21.57 8.32 22.88 8.3C24.19 8.27 25.63 8.2 27 8.23C28.37 8.27 29.81 8.42 31.11 8.51C32.42 8.61 33.54 8.75 34.85 8.8C36.16 8.85 37.78 8.64 38.98 8.81C40.17 8.98 41.45 9.06 42.02 9.82C42.58 10.58 42.28 11.87 42.34 13.36C42.41 14.84 42.38 16.86 42.4 18.75C42.42 20.63 42.47 22.92 42.48 24.64C42.5 26.36 42.77 27.82 42.5 29.06C42.22 30.3 41.68 31.61 40.85 32.1C40.02 32.58 38.06 31.99 37.5 31.97C36.95 31.96 37.5 32 37.5 32" />
      <path d="M11.44 24.27Q19.18 23.77 26.93 23.65" />
      <path d="M11.49 30.4Q16.75 30.25 22.02 30.22" />
      </symbol>
      <symbol id="d-dong-ho-cat" viewBox="0 0 48 48">
      <path d="M11.1 5.83Q23.9 6.66 36.72 6.65" />
      <path d="M11.18 41.74Q23.94 41.28 36.69 41.7" />
      <path d="M15.01 6.5C15.02 7.05 14.81 8.64 15.07 9.79C15.34 10.93 15.98 12.07 16.6 13.37C17.21 14.68 17.95 16.23 18.76 17.61C19.57 18.98 20.48 20.69 21.46 21.61C22.43 22.54 23.63 23.31 24.59 23.16C25.54 23 26.28 21.8 27.19 20.71C28.1 19.62 29.18 17.92 30.06 16.61C30.93 15.3 31.82 14.12 32.46 12.85C33.09 11.57 33.73 10.01 33.85 8.95C33.97 7.88 33.31 6.89 33.16 6.48C33.02 6.08 33.03 6.5 33 6.5" />
      <path d="M15.12 41.48C15.11 40.94 14.85 39.37 15.08 38.21C15.3 37.06 15.88 35.88 16.48 34.57C17.09 33.26 17.88 31.72 18.71 30.36C19.54 29 20.49 27.33 21.47 26.4C22.45 25.48 23.62 24.68 24.59 24.81C25.57 24.94 26.39 26.1 27.34 27.17C28.29 28.25 29.41 29.94 30.29 31.26C31.17 32.58 32.02 33.78 32.6 35.08C33.18 36.38 33.71 37.98 33.79 39.06C33.87 40.13 33.21 41.1 33.08 41.51C32.94 41.91 33.01 41.5 33 41.5" />
      <path d="M18.49 37.98C19.04 37.67 20.67 36.5 21.8 36.11C22.94 35.72 24.14 35.45 25.3 35.66C26.47 35.87 28.08 36.98 28.78 37.37C29.48 37.76 29.38 37.9 29.5 38" />
      <circle cx="24" cy="30.5" r="1.5" fill="currentColor" stroke="none" />
      </symbol>
      <symbol id="d-but-chi" viewBox="0 0 48 48">
      <path d="M4.61 36.98Q13.91 27.17 23.73 17.87Q28.07 16.46 32.5 15.32Q31.46 19.65 30.33 23.95Q21.01 34.02 10.97 43.36Q7.81 40.15 4.61 36.98Z" />
      <path d="M24.09 17.43Q27.05 20.88 30.06 24.28" />
      <path d="M8.1 33.18Q11.29 36.3 14.45 39.44" />
      <path d="M28.52 16.65Q30.07 18.03 31.62 19.4" />
      </symbol>
      <symbol id="d-dua-phep" viewBox="0 0 48 48">
      <path d="M7.22 40.92Q17.78 30.57 27.78 19.68" />
      <path d="M23.25 21.48Q25.2 23.1 27.15 24.72" />
      <path d="M35.78 4.35Q36.67 7.62 37.54 10.9Q40.84 11.65 44.17 12.25Q40.85 12.91 37.54 13.63Q36.79 16.99 35.87 20.31Q35.26 16.77 34.8 13.21Q31.51 12.65 28.23 12.07Q31.3 11.31 34.34 10.44Q35.12 7.41 35.78 4.35Z" />
      <circle cx="42.5" cy="25" r="1.9" fill="currentColor" stroke="none" />
      <circle cx="23" cy="7" r="1.6" fill="currentColor" stroke="none" />
      </symbol>
      <symbol id="d-cham-hoi" viewBox="0 0 48 48">
      <path d="M15.17 12.62C15.42 12.12 16 10.48 16.69 9.65C17.38 8.83 18.38 8.19 19.31 7.68C20.24 7.16 21.26 6.77 22.28 6.55C23.31 6.33 24.44 6.21 25.48 6.36C26.52 6.5 27.64 6.87 28.53 7.42C29.43 7.97 30.23 8.81 30.85 9.65C31.48 10.5 31.93 11.51 32.26 12.51C32.6 13.52 32.79 14.6 32.85 15.68C32.91 16.77 33.11 17.98 32.63 19C32.15 20.02 30.85 21 29.95 21.8C29.06 22.61 28.18 23.08 27.26 23.81C26.34 24.54 25.02 25.3 24.45 26.2C23.88 27.09 23.91 28.45 23.83 29.17C23.75 29.88 23.97 30.28 24 30.5" />
      <circle cx="24" cy="39" r="2.4" fill="currentColor" stroke="none" />
      </symbol>
      <symbol id="d-mui-ten-cong" viewBox="0 0 48 48">
      <path d="M4.98 38C5.12 37.41 5.48 35.72 5.81 34.49C6.15 33.26 6.57 31.91 7.02 30.62C7.46 29.34 7.94 27.99 8.48 26.79C9.02 25.58 9.56 24.51 10.25 23.39C10.93 22.27 11.71 21.09 12.59 20.08C13.47 19.07 14.5 18.11 15.53 17.34C16.55 16.58 17.62 16.02 18.73 15.48C19.83 14.93 20.99 14.48 22.16 14.08C23.33 13.68 24.56 13.27 25.73 13.07C26.9 12.88 28.1 12.74 29.2 12.89C30.3 13.05 31.31 13.47 32.35 14.03C33.39 14.58 34.46 15.52 35.45 16.24C36.44 16.95 37.51 17.87 38.27 18.33C39.03 18.79 39.71 18.89 40 19" />
      <path d="M32.24 21.48Q36.27 20.23 40.38 19.27Q39.07 15.22 37.78 11.17" />
      </symbol>
      <symbol id="d-vong-khoanh" viewBox="0 0 48 48">
      <path d="M6.21 22.37C6.45 21.82 7.01 20.07 7.63 19.07C8.26 18.08 9.08 17.17 9.97 16.4C10.86 15.62 11.92 14.97 12.97 14.43C14.01 13.9 15.16 13.52 16.25 13.19C17.34 12.86 18.41 12.66 19.51 12.45C20.6 12.25 21.73 12.09 22.84 11.96C23.96 11.84 25.1 11.74 26.21 11.73C27.33 11.72 28.46 11.75 29.54 11.89C30.62 12.02 31.62 12.21 32.7 12.53C33.78 12.86 35 13.33 36.03 13.83C37.05 14.32 37.95 14.85 38.86 15.52C39.76 16.18 40.72 16.98 41.46 17.82C42.2 18.67 42.86 19.51 43.29 20.57C43.71 21.63 44.02 23.03 44 24.19C43.99 25.36 43.67 26.53 43.21 27.57C42.75 28.61 42.01 29.59 41.24 30.44C40.47 31.3 39.52 32.03 38.59 32.71C37.66 33.39 36.65 33.96 35.66 34.5C34.66 35.04 33.69 35.52 32.64 35.95C31.58 36.39 30.48 36.81 29.34 37.13C28.21 37.44 27.02 37.7 25.84 37.85C24.65 38.01 23.43 38.07 22.24 38.06C21.05 38.06 19.86 37.96 18.7 37.84C17.55 37.72 16.4 37.55 15.3 37.34C14.19 37.13 13.13 36.92 12.05 36.59C10.98 36.25 9.85 35.87 8.84 35.31C7.84 34.76 6.81 34.08 6 33.26C5.2 32.44 4.46 31.44 3.99 30.4C3.51 29.35 3.23 28.13 3.15 26.99C3.08 25.86 3.26 24.68 3.54 23.6C3.82 22.52 4.28 21.5 4.82 20.52C5.35 19.55 6.02 18.61 6.76 17.76C7.51 16.91 8.34 16.12 9.26 15.41C10.19 14.71 11.43 14.06 12.31 13.55C13.18 13.03 14.16 12.57 14.52 12.35C14.88 12.14 14.47 12.26 14.47 12.24" />
      </symbol>
      <symbol id="d-lap-lanh" viewBox="0 0 48 48">
      <path d="M18.8 12.89Q20.23 18.63 21.62 24.38Q27.19 25.6 32.71 27Q27.04 28.52 21.3 29.79Q20.34 35.51 18.89 41.13Q17.75 35.35 16.44 29.61Q10.89 28.14 5.32 26.77Q10.89 25.76 16.32 24.16Q17.81 18.58 18.8 12.89Z" />
      <path d="M36.73 3.57Q37.25 6.13 37.83 8.68Q40.76 9.52 43.7 10.34Q40.85 10.64 37.99 10.84Q37.38 13.57 36.67 16.27Q36.31 13.79 35.9 11.32Q33.36 10.83 30.84 10.29Q33.22 9.6 35.59 8.91Q36.16 6.24 36.73 3.57Z" />
      <circle cx="39" cy="26" r="1.7" fill="currentColor" stroke="none" />
      </symbol>
      <symbol id="d-kinh-lup" viewBox="0 0 48 48">
      <path d="M29.48 27.94C29.02 28.31 27.68 29.5 26.74 30.15C25.81 30.8 24.9 31.39 23.87 31.83C22.84 32.28 21.72 32.67 20.59 32.83C19.45 32.99 18.21 33 17.08 32.78C15.94 32.56 14.78 32.1 13.78 31.51C12.78 30.93 11.86 30.11 11.08 29.27C10.3 28.42 9.64 27.44 9.1 26.44C8.56 25.44 8.11 24.37 7.82 23.28C7.52 22.19 7.33 21.03 7.33 19.9C7.34 18.77 7.51 17.59 7.85 16.53C8.19 15.46 8.73 14.41 9.35 13.48C9.97 12.56 10.76 11.72 11.57 10.97C12.39 10.21 13.29 9.54 14.25 8.96C15.21 8.38 16.25 7.84 17.34 7.49C18.43 7.14 19.63 6.87 20.8 6.85C21.97 6.82 23.23 6.99 24.35 7.36C25.48 7.72 26.59 8.34 27.54 9.04C28.49 9.74 29.33 10.64 30.05 11.57C30.77 12.5 31.38 13.54 31.86 14.6C32.33 15.67 32.71 16.82 32.9 17.97C33.09 19.12 33.14 20.34 32.98 21.49C32.83 22.64 32.47 23.81 31.98 24.86C31.5 25.9 30.8 26.88 30.06 27.74C29.32 28.61 28.36 29.38 27.56 30.06C26.76 30.75 25.64 31.54 25.27 31.86C24.9 32.18 25.33 31.97 25.34 31.99" />
      <path d="M29.24 29.75Q35.36 35.52 41.24 41.55" />
      <path d="M13.18 18.81C13.3 18.57 13.64 17.84 13.9 17.39C14.16 16.95 14.43 16.53 14.74 16.14C15.06 15.75 15.4 15.39 15.77 15.06C16.15 14.73 16.57 14.45 16.98 14.16C17.39 13.88 18.03 13.51 18.23 13.35C18.43 13.2 18.2 13.26 18.19 13.24" />
      </symbol>
      <symbol id="d-trai-tim" viewBox="0 0 48 48">
      <path d="M23.83 15.88C23.94 15.41 24 13.99 24.51 13.08C25.01 12.18 25.98 11.16 26.86 10.43C27.75 9.7 28.78 9.12 29.83 8.71C30.89 8.29 32.08 7.96 33.2 7.95C34.32 7.94 35.53 8.18 36.54 8.65C37.55 9.12 38.5 9.95 39.26 10.76C40.02 11.57 40.62 12.54 41.1 13.5C41.58 14.47 42.01 15.49 42.15 16.54C42.28 17.6 42.22 18.81 41.91 19.85C41.61 20.89 40.95 21.87 40.32 22.79C39.69 23.72 38.87 24.54 38.14 25.41C37.41 26.28 36.67 27.18 35.93 28.01C35.2 28.83 34.52 29.61 33.72 30.37C32.91 31.13 31.96 31.83 31.1 32.56C30.24 33.3 29.33 33.96 28.55 34.78C27.76 35.6 27 36.57 26.4 37.48C25.79 38.39 25.48 39.82 24.93 40.26C24.39 40.7 23.67 40.6 23.1 40.1C22.54 39.6 22.19 38.16 21.52 37.26C20.86 36.37 19.94 35.52 19.1 34.74C18.27 33.95 17.37 33.35 16.49 32.56C15.61 31.76 14.62 30.83 13.82 29.99C13.02 29.16 12.42 28.36 11.68 27.55C10.94 26.73 10.12 25.92 9.39 25.07C8.65 24.22 7.81 23.39 7.26 22.44C6.7 21.49 6.24 20.42 6.05 19.37C5.87 18.31 5.97 17.17 6.15 16.13C6.34 15.09 6.69 14.09 7.17 13.14C7.66 12.18 8.27 11.15 9.07 10.4C9.87 9.64 10.93 8.96 11.97 8.6C13 8.24 14.14 8.16 15.27 8.22C16.4 8.29 17.66 8.59 18.73 9C19.8 9.42 20.84 9.97 21.68 10.72C22.52 11.47 23.33 12.69 23.76 13.49C24.18 14.29 24.2 15.17 24.26 15.51C24.32 15.85 24.13 15.51 24.11 15.51" />
      </symbol>
      <symbol id="d-tia-set" viewBox="0 0 48 48">
      <path d="M27.91 3.79Q19.49 15.43 10.82 26.89Q16.43 26.46 22.06 26.48Q19.56 35.28 16.74 43.98Q26.88 31.25 36.79 18.33Q31.17 18.63 25.55 18.85Q27.54 11.47 29.98 4.23Q28.95 3.98 27.91 3.79Z" />
      </symbol>
      <symbol id="d-may" viewBox="0 0 48 48">
      <path d="M11.81 35.82C11.29 35.64 9.61 35.33 8.71 34.75C7.8 34.16 6.89 33.25 6.4 32.28C5.91 31.32 5.71 30.05 5.75 28.96C5.79 27.86 6.14 26.72 6.63 25.74C7.12 24.75 7.92 23.86 8.69 23.06C9.46 22.26 10.39 21.78 11.26 20.93C12.13 20.08 13.16 18.91 13.92 17.98C14.68 17.04 15.13 16.13 15.83 15.31C16.53 14.49 17.27 13.71 18.12 13.07C18.97 12.44 19.92 11.83 20.91 11.5C21.91 11.17 23.06 11.01 24.1 11.09C25.14 11.16 26.2 11.53 27.15 11.93C28.1 12.34 28.96 12.88 29.78 13.52C30.61 14.16 31.32 14.96 32.09 15.78C32.86 16.6 33.63 17.56 34.4 18.45C35.17 19.33 35.84 20.45 36.71 21.1C37.57 21.76 38.77 21.76 39.62 22.39C40.47 23.03 41.27 23.93 41.81 24.9C42.35 25.87 42.81 27.08 42.85 28.21C42.88 29.34 42.57 30.67 42.03 31.67C41.49 32.67 40.52 33.58 39.59 34.23C38.67 34.87 37.64 35.24 36.47 35.55C35.3 35.85 33.78 35.92 32.57 36.06C31.37 36.19 30.39 36.32 29.24 36.36C28.09 36.39 26.81 36.32 25.66 36.26C24.51 36.21 23.49 36.07 22.33 36.02C21.17 35.97 19.88 35.97 18.71 35.97C17.55 35.96 16.3 36 15.34 35.99C14.39 35.98 13.39 35.91 13 35.92C12.61 35.92 13 35.99 13 36" />
      </symbol>
      <symbol id="d-la-cay" viewBox="0 0 48 48">
      <path d="M8.02 41C7.92 40.21 7.61 37.94 7.41 36.29C7.2 34.63 6.91 32.77 6.8 31.07C6.7 29.36 6.58 27.58 6.77 26.06C6.97 24.53 7.37 23.26 7.95 21.91C8.52 20.57 9.34 19.21 10.22 18C11.11 16.79 12.21 15.64 13.28 14.67C14.35 13.7 15.46 12.87 16.64 12.17C17.82 11.47 19.09 10.96 20.36 10.46C21.63 9.97 22.98 9.58 24.26 9.19C25.55 8.8 26.81 8.48 28.07 8.14C29.34 7.81 30.56 7.46 31.87 7.16C33.18 6.86 34.62 6.44 35.96 6.35C37.29 6.26 39.02 6.14 39.87 6.62C40.72 7.11 40.91 8.09 41.06 9.27C41.22 10.44 41 12.1 40.8 13.67C40.61 15.25 40.25 17.17 39.89 18.71C39.52 20.25 39.14 21.63 38.62 22.92C38.1 24.21 37.48 25.32 36.77 26.42C36.06 27.52 35.21 28.55 34.37 29.54C33.52 30.53 32.64 31.46 31.71 32.36C30.78 33.27 29.85 34.14 28.8 34.96C27.75 35.78 26.57 36.58 25.41 37.26C24.24 37.94 22.98 38.54 21.79 39.02C20.59 39.5 19.46 39.86 18.26 40.12C17.05 40.37 15.76 40.46 14.56 40.55C13.36 40.65 12.16 40.64 11.07 40.71C9.98 40.78 8.51 40.93 8 40.98C7.49 41.03 8 41 8 41" />
      <path d="M4.94 43.95C5.38 43.3 6.59 41.4 7.58 40.06C8.58 38.72 9.71 37.29 10.92 35.91C12.13 34.53 13.48 33.15 14.86 31.79C16.23 30.44 18.06 28.84 19.2 27.79C20.33 26.74 20.84 26.27 21.66 25.49C22.48 24.7 23.11 24.02 24.11 23.1C25.11 22.19 26.52 21 27.68 19.99C28.84 18.99 30.53 17.59 31.08 17.09C31.63 16.59 31.01 17.01 31 17" />
      <path d="M18.27 29.25Q22.7 29.57 27.12 29.89" />
      <path d="M24 23.2Q23.72 19.03 23.48 14.87" />
      </symbol>
      <symbol id="d-mu-tot-nghiep" viewBox="0 0 48 48">
      <path d="M24.04 9.18Q34.21 13.29 44.03 18.17Q33.95 23.2 23.9 28.31Q14.06 22.95 3.84 18.35Q13.81 13.48 24.04 9.18Z" />
      <path d="M12.02 23C11.91 23.62 11.42 25.44 11.35 26.7C11.27 27.96 11.06 29.45 11.56 30.55C12.06 31.65 13.26 32.52 14.34 33.3C15.42 34.08 16.73 34.75 18.03 35.22C19.33 35.69 20.84 36.03 22.13 36.12C23.43 36.22 24.55 36.05 25.81 35.79C27.07 35.53 28.45 35.06 29.72 34.57C30.98 34.08 32.31 33.55 33.4 32.86C34.49 32.17 35.74 31.44 36.23 30.42C36.73 29.4 36.43 27.97 36.36 26.74C36.29 25.51 35.87 23.66 35.81 23.04C35.75 22.41 35.97 23.01 36 23" />
      <path d="M44.3 18.71Q44.47 24.77 44.44 30.82" />
      <circle cx="44.5" cy="34" r="2.4" fill="currentColor" stroke="none" />
      </symbol>
      <symbol id="d-star" viewBox="0 0 100 100">
      <path d="M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z" />
      </symbol>
        </defs>
      </svg>
<header className="hero" id="dau-trang" data-hero="">
<div className="hero-dots" aria-hidden="true">
</div>
<div className="hero-disc" aria-hidden="true">
</div>
<div className="hero-in">
<nav className="bar" aria-label="Chính">
<a className="wm" href="#dau-trang">
Essity
</a>
<div className="bar-r">
<button className="pause" type="button" aria-pressed="false" aria-label="Tạm dừng chuyển động" title="Tạm dừng chuyển động" data-pause="">
<svg className="ic-pause" viewBox="0 0 24 24" aria-hidden="true">
<path d="M8 5v14M16 5v14" />
</svg>
<svg className="ic-play" viewBox="0 0 24 24" aria-hidden="true">
<path d="M8 5l11 7-11 7z" />
</svg>
</button>
<Link className="login" href="/login">
Đăng nhập
</Link>
</div>
</nav>
<div className="hero-main">
<div className="hero-text">
<h1>
<span className="ln">
<span style={v({ "--i": "0" })}>
Hôm nay ôn gì,
</span>
</span>
{" "}
<span className="ln">
<span style={v({ "--i": "1" })}>
đã có
{" "}
<span className="ul-w">
tôi lo!
<svg className="ul" viewBox="0 0 320 20" preserveAspectRatio="none" aria-hidden="true" focusable="false">
<path pathLength="1" d="M4 13 C 70 4, 150 17, 220 9 S 300 6, 316 11" />
</svg>
</span>
</span>
</span>
</h1>
<p className="lead rise" style={v({ "--d": "420ms" })}>
Trợ lí học tập tiên tiến. Quản lí lịch ôn luyện hiệu quả với thuật toán FSRS và đồ thị tri thức.
</p>
<div className="buy rise" style={v({ "--d": "540ms" })}>
<Link className="cta" href="/register">
Đăng ký
</Link>
</div>
</div>
<svg className="m-sticker" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
<path d="M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z" />
</svg>
<div className="hero-pic" aria-hidden="true">
<svg className="m-star" viewBox="0 0 62 62" focusable="false">
<path pathLength="1" d="M31 4 L38.5 23 L58 24.5 L42.5 37 L48 56.5 L31 45.5 L13.5 57 L19.5 37.5 L3.5 25.5 L23.5 23.5 Z" />
</svg>
<div className="mascot-wrap">
<div className="bubble">
Xin chào, rất vui được gặp bạn
</div>
<Mascot kind="cloud" pose="chao" tone="solid" size="lg" className="mascot size-full" />
</div>
<div className="note-chip" data-ui="1">
<b>
Mây Mây – trợ lí học tập của bạn
</b>
<span>
Học tập thật dễ và vui!
</span>
</div>
</div>
</div>
</div>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "46%", top: "13%", width: "54px", height: "54px", rotate: "-8deg" }}>
<use href="#d-lap-lanh" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "5%", top: "80%", width: "60px", height: "60px", rotate: "8deg" }}>
<use href="#d-kinh-lup" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "92%", top: "10%", width: "46px", height: "46px", rotate: "10deg" }}>
<use href="#d-trai-tim" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "56%", top: "86%", width: "52px", height: "52px", rotate: "-6deg" }}>
<use href="#d-tia-set" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "20%", top: "8%", width: "56px", height: "56px", rotate: "-4deg" }}>
<use href="#d-may" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "88%", top: "78%", width: "54px", height: "54px", rotate: "12deg" }}>
<use href="#d-la-cay" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "30%", top: "88%", width: "48px", height: "48px", rotate: "6deg" }}>
<use href="#d-kep-giay" />
</svg>
<svg className="deco" viewBox="0 0 48 48" aria-hidden="true" style={{ left: "72%", top: "7%", width: "52px", height: "52px", rotate: "-10deg" }}>
<use href="#d-mu-tot-nghiep" />
</svg>
</header>
<main>
<section className="feat f-graph" id="do-thi" aria-labelledby="h-graph" data-feat="">
<span className="pat-w r" aria-hidden="true">
</span>
<div className="wrap">
<div className="f-head">
<svg className="doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-do-thi" />
</svg>
<h2 id="h-graph">
Đồ thị
{" "}
<span className="uw">
tri thức
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<p>
Kết nối kiến thức hiển thị trực quan, dễ dàng hệ thống hóa kiến thức.
</p>
</div>
<div data-ui="1" className="graph-stage" data-graph="">
<svg className="gsvg" role="img" aria-label="Đồ thị tri thức: ba môn và các thẻ kiến thức nối với nhau, kéo thả được">
</svg>
<div className="gtip" role="status" aria-live="polite" hidden>
</div>
</div>
</div>
</section>
<section className="feat f-out" id="de-cuong" aria-labelledby="h-out" data-feat="">
<span className="pat l" aria-hidden="true">
</span>
<div className="wrap split">
<div className="f-head">
<svg className="doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-kep-giay" />
</svg>
<h2 id="h-out">
Tự tách
{" "}
<span className="uw">
đề cương
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<p>
Tải giáo trình lên, đề cương hiện ra từng mục. Thấy chưa đúng thì chat để chỉnh.
</p>
</div>
<div className="panel out-demo" data-out="" aria-hidden="true">
<div data-ui="1" className="pdf">
<div className="pdf-bar">
<span>
</span>
<span>
</span>
<span>
</span>
<em>
Vat-ly-doi-song.pdf
</em>
</div>
<div className="pdf-page">
<p className="ph1" data-h="0">
Chương 1. Ánh sáng quanh ta
</p>
<i>
</i>
<i>
</i>
<i className="s">
</i>
<p className="ph2" data-h="1">
1.1 Vì sao bầu trời màu xanh?
</p>
<i>
</i>
<i className="s">
</i>
<p className="ph2" data-h="2">
1.2 Cầu vồng hình thành thế nào?
</p>
<i>
</i>
<i>
</i>
<i className="s">
</i>
<p className="ph1" data-h="3">
Chương 2. Nước và nhiệt
</p>
<i>
</i>
<i className="s">
</i>
<p className="ph2" data-h="4">
2.1 Hiệu ứng Mpemba
</p>
<i>
</i>
<i>
</i>
<i className="s">
</i>
<p className="ph2" data-h="5">
2.2 Vì sao mật ong không hỏng?
</p>
<i>
</i>
<i className="s">
</i>
<div className="scan">
</div>
</div>
</div>
<svg className="out-arrow" viewBox="0 0 80 40" aria-hidden="true">
<path pathLength="1" d="M4 22 C26 6 52 6 74 20" />
<path pathLength="1" d="M62 10 L75 21 L60 28" />
</svg>
<div data-ui="1" className="tree">
<p className="tree-t">
Đề cương
</p>
<ul>
<li data-t="0" className="l1">
<b>
1
</b>
Ánh sáng quanh ta
<ul>
<li data-t="1" className="l2">
<b>
1.1
</b>
Vì sao bầu trời màu xanh?
</li>
<li data-t="2" className="l2">
<b>
1.2
</b>
Cầu vồng hình thành thế nào?
</li>
</ul>
</li>
<li data-t="3" className="l1">
<b>
2
</b>
Nước và nhiệt
<ul>
<li data-t="4" className="l2">
<b>
2.1
</b>
Hiệu ứng Mpemba
</li>
<li data-t="5" className="l2">
<b className="ringed">
2.2
<svg viewBox="0 0 48 48" className="ring" preserveAspectRatio="none" aria-hidden="true">
<use href="#d-vong-khoanh" />
</svg>
</b>
Vì sao mật ong không hỏng?
</li>
</ul>
</li>
</ul>
<div className="chatbar">
<span data-chat2="">
chuyển mục 2.2 lên chương 1
</span>
</div>
</div>
</div>
</div>
</section>
<section className="feat f-card" id="the-nguon" aria-labelledby="h-card" data-feat="">
<span className="pat r" aria-hidden="true">
</span>
<div className="wrap split rev">
<div className="f-head">
<svg className="doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-the" />
</svg>
<h2 id="h-card">
Chia thẻ kiến thức
{" "}
<span className="uw">
thông minh
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<p>
AI tự động chia kiến thức thành các thẻ ghi nhớ, sẵn sàng cho việc recall. Người dùng có thể chỉnh sửa thẻ bằng markdown.
</p>
</div>
<div className="panel card-demo" data-card="" aria-hidden="true">
<div data-ui="1" className="md">
<p className="md-cap">
Bạn viết
</p>
<pre>
<code data-md="">
</code>
</pre>
</div>
<div className="rcard" data-ui="1">
<p className="rc-meta">
Thẻ · Vật lý đời sống
</p>
<h3>
Công thức Einstein
</h3>
<ul>
<li>
Năng lượng nằm sẵn trong khối lượng.
</li>
<li>
<b>
Một hạt gạo
</b>
{" "}
chứa năng lượng cỡ một thành phố nhỏ dùng cả ngày.
</li>
</ul>
<p className="rc-f" data-tex="E=mc^2">
E = mc²
</p>
<div className="src-row">
<button className="src-b ringed" type="button" tabIndex={-1}>
Nguồn · tr. 3
<svg className="h-ul s" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" />
</svg>
</button>
</div>
<div className="src-pop">
<small>
Giáo trình Vật lý đời sống · trang 3
</small>
<span>
…
{" "}
<mark>
khối lượng và năng lượng là hai mặt của một đại lượng
</mark>
, nối với nhau qua bình phương tốc độ ánh sáng …
</span>
</div>
</div>
</div>
</div>
</section>
<section className="feat f-fsrs" id="lich-on" aria-labelledby="h-fsrs" data-feat="">
<span className="pat l" aria-hidden="true">
</span>
<div className="wrap">
<div className="f-head wide">
<svg className="doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-dong-ho-cat" />
</svg>
<h2 id="h-fsrs">
Lịch ôn
{" "}
<span className="uw">
FSRS
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<p>
Trí nhớ phai theo đường cong. Essity ôn lại đúng lúc sắp quên, nên mỗi lần nhớ được lâu hơn.
</p>
</div>
<div className="panel fsrs-demo" data-fsrs="" aria-hidden="true">
<svg className="curve" viewBox="0 0 900 300" preserveAspectRatio="none">
<g className="grid">
<path d="M0 60H900M0 150H900M0 240H900" />
</g>
<path className="c-line" pathLength="1" d={CURVE.d} />
<g className="c-dots">
{CURVE.dots.map((x) => (
<circle key={x} cx={x} cy={CURVE.y1} r={7} />
))}
</g>
<circle cx={CURVE.trough.x} cy={CURVE.trough.y} r={17} className="rev-ring" />
</svg>
<div className="curve-lab">
<span>
Nhớ rõ
</span>
<span>
Quên
</span>
</div>
<div className="days">
<span>
Hôm nay
</span>
<span>
Ngày mai
</span>
<span>
3 ngày
</span>
<span>
1 tuần
</span>
<span>
3 tuần
</span>
</div>
<div data-ui="1" className="queue">
<div className="qc" data-q="0">
Bầu trời xanh
</div>
<div className="qc" data-q="1">
Bạch tuộc 3 tim
</div>
<div className="qc" data-q="2">
Mật ong
</div>
<div className="qc" data-q="3">
Hiệu ứng Mpemba
</div>
<div className="qc" data-q="4">
Bernoulli
</div>
</div>
<span className="hand" data-fsrs-hand="" aria-hidden="true">
<svg viewBox="0 0 48 48" className="ha a-ul">
<use href="#d-mui-ten-cong" />
</svg>
<em>
ôn đúng lúc sắp quên
</em>
</span>
</div>
</div>
</section>
<section className="feat f-prac" id="luyen-de" aria-labelledby="h-prac" data-feat="">
<span className="pat-w r" aria-hidden="true">
</span>
<div className="wrap split">
<div className="f-head">
<svg className="doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-but-chi" />
</svg>
<h2 id="h-prac">
Luyện đúng
{" "}
<span className="uw">
dạng đề
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<p>
Tải đề mẫu, app tách từng câu, gom theo dạng và gợi ý câu nên luyện trước. Mỗi câu có lịch ôn riêng.
</p>
</div>
<div className="panel prac-demo" data-prac="" aria-hidden="true">
<div data-ui="1" className="lanes">
<div className="lane" data-l="0">
<h3>
Tính toán
</h3>
<div className="slot">
</div>
</div>
<div className="lane" data-l="1">
<h3>
Giải thích
</h3>
<div className="slot">
</div>
</div>
<div className="lane" data-l="2">
<h3>
So sánh
</h3>
<div className="slot">
</div>
</div>
</div>
<div className="pool">
<div className="qt" data-to="0">
Hình tròn bán kính 5 cm có diện tích bao nhiêu?
</div>
<div className="qt" data-to="1">
Vì sao bạch tuộc có ba trái tim?
</div>
<div className="qt" data-to="2">
So sánh mật ong và đường về khả năng bảo quản.
</div>
<div className="qt" data-to="1">
Vì sao máy bay bay được? (Bernoulli)
</div>
<div className="qt" data-to="0">
Quả cầu nặng 2 kg ở độ cao 10 m có thế năng bao nhiêu?
</div>
</div>
<div className="verdict">
<span className="flip">
<i className="ok">
<svg viewBox="0 0 16 16">
<path d="M3 8.5 L6.5 12 L13 4.5" />
</svg>
Đúng
</i>
<i className="near">
≈ Gần đúng
</i>
</span>
<span className="sugg">
→ Gợi ý: làm câu tính toán trước
</span>
</div>
<span className="hand" aria-hidden="true" style={{ left: "3%", bottom: "12px", rotate: "-3deg" }}>
<svg viewBox="0 0 48 48" className="ha a-ul">
<use href="#d-mui-ten-cong" />
</svg>
<em>
chấm từng ý
</em>
</span>
</div>
</div>
</section>
<section className="feat f-nl" id="chinh-sua" aria-labelledby="h-nl" data-feat="">
<span className="pat l" aria-hidden="true">
</span>
<div className="wrap split rev">
<div className="f-head">
<svg className="doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-dua-phep" />
</svg>
<h2 id="h-nl">
Chỉnh sửa
{" "}
<span className="uw">
đơn giản
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<p>
Tất cả thao tác chỉnh sửa chỉ cần viết ra yêu cầu và trợ lí AI sẽ hỗ trợ hoàn thành.
</p>
</div>
<div className="panel nl-demo" data-nl="">
<div className="nl-in">
<span data-nl-text="" className="ringed" aria-hidden="true">
mục hiệu ứng Mpemba tôi học rồi
<svg className="h-ul s" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" />
</svg>
</span>
<kbd aria-hidden="true">
⏎
</kbd>
</div>
<ul data-ui="1" className="nl-list" aria-hidden="true">
<li data-r="0">
<span>
1.1
</span>
Vì sao bầu trời màu xanh?
<i className="st done">
Đã học
</i>
</li>
<li data-r="1">
<span>
1.2
</span>
Cầu vồng hình thành thế nào?
<i className="st done">
Đã học
</i>
</li>
<li data-r="2" className="target on">
<span>
2.1
</span>
Hiệu ứng Mpemba
<i className="st todo" data-st="">
Chưa học
</i>
</li>
<li data-r="3">
<span>
2.2
</span>
Vì sao mật ong không hỏng?
<i className="st todo">
Chưa học
</i>
</li>
</ul>
<div className="nl-diff v on" data-diff="" aria-live="polite">
<p>
<b>
Xem trước thay đổi
</b>
</p>
<p className="dl">
Mục 2.1 · Hiệu ứng Mpemba:
{" "}
<s>
Chưa học
</s>
{" "}
→
{" "}
<strong>
Đã học
</strong>
</p>
<div className="nl-act">
<button type="button" className="b-pri" data-apply="">
Áp dụng
</button>
<button type="button" className="b-sec" data-undo="">
Hoàn tác
</button>
</div>
</div>
</div>
</div>
</section>
<section className="try wrap" id="thu-cham" aria-labelledby="h-try">
<span className="pat r" aria-hidden="true">
</span>
<h2 id="h-try">
Viết ra, rồi
{" "}
<span className="uw">
được chấm
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<div className="sheet-t" data-ui="1" data-try="">
<div className="qcol">
<p className="q">
Vì sao bầu trời có màu xanh?
</p>
<label className="ans">
<span className="sr">
Câu trả lời của bạn
</span>
<textarea rows={3} aria-label="Câu trả lời" defaultValue="Vì ánh sáng Mặt Trời bị không khí làm tán xạ." />
</label>
<p className="q-meta">
Môn Vật lý đời sống, câu 3
</p>
<button className="btn-p" type="button" data-grade="">
Chấm
</button>
</div>
<div className="rcol" data-result="">
<p className="verdict-b">
<span className="vb">
≈ Đúng một phần
</span>
</p>
<p className="miss">
<b>
Còn thiếu:
</b>
{" "}
ánh sáng xanh bị tán xạ mạnh hơn các màu khác.
</p>
<p className="src-l">
Giáo trình Vật lý đời sống · trang 12
</p>
<p className="src-t">
Không khí tán xạ ánh sáng;
{" "}
<mark>
bước sóng ngắn như xanh lam bị tán xạ mạnh hơn bước sóng dài như đỏ
</mark>
, nên cả bầu trời ánh lên màu xanh.
</p>
<button className="lnk" type="button">
Chấm sai
</button>
</div>
</div>
</section>
<section className="faq wrap" id="hoi-dap" aria-labelledby="h-faq">
<span className="pat l" aria-hidden="true">
</span>
<svg className="qmark doodle" viewBox="0 0 48 48" aria-hidden="true">
<use href="#d-cham-hoi" />
</svg>
<h2 id="h-faq">
Hỏi
{" "}
<span className="uw">
đáp
<svg className="h-ul" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">
<path d="M3 8 C 40 2, 80 12, 120 6 S 180 4, 197 8" pathLength="1" />
</svg>
</span>
</h2>
<dl>
<div>
<dt>
Thẻ kiến thức từ đâu?
</dt>
<dd>
AI soạn từ buổi học bạn ghi, mỗi thẻ có trang nguồn và nằm thẳng trong Kho. Bạn sửa hoặc xóa bất kỳ lúc nào.
</dd>
</div>
<div>
<dt>
Cần chuẩn bị gì?
</dt>
<dd>
Tên môn, ngày thi và giáo trình chính, vì có giáo trình app mới lập được đề cương. Đề thi mẫu và ảnh vở thêm lúc nào cũng được.
</dd>
</div>
<div>
<dt>
AI chấm sai thì sao?
</dt>
<dd>
Mỗi lời chấm kèm trang nguồn để bạn đối chiếu. Thấy chưa đúng thì bấm Chấm sai, lịch ôn sẽ không bị ảnh hưởng.
</dd>
</div>
<div>
<dt>
Lịch ôn dựa trên gì?
</dt>
<dd>
Trên FSRS, thuật toán lặp lại ngắt quãng đã được công bố, và trên kết quả chấm thật của bạn. Không câu nào xếp sau ngày thi.
</dd>
</div>
<div>
<dt>
Nghỉ vài hôm thì sao?
</dt>
<dd>
Mở lại là app gợi ý đúng chỗ bạn dừng.
</dd>
</div>
</dl>
</section>
</main>
<footer className="end" id="cuoi" aria-labelledby="h-end" data-end="">
<svg className="fs fs1" viewBox="0 0 100 100" aria-hidden="true">
<use href="#d-star" />
</svg>
<svg className="fs fs2" viewBox="0 0 100 100" aria-hidden="true">
<use href="#d-star" />
</svg>
<div className="wrap end-main">
<h2 id="h-end">
Tối nay mở app, việc đầu tiên đã nằm sẵn
</h2>
<div className="end-act">
<Link className="cta2" href="/register">
Đăng ký
</Link>
<p>
Đã có tài khoản?
{" "}
<Link href="/login">
Đăng nhập
</Link>
</p>
</div>
</div>
<div className="wrap legal">
<span>
© 2026 Essity
</span>
</div>
<div className="wmmask">
<p className="wmbig" aria-hidden="true">
</p>
</div>
</footer>
      <LandingMotion />
    </div>
  );
}
