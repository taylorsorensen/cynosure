import React, { useEffect, useRef } from 'react';
import { AvatarEvent } from './types';

interface Props {
  analyser: AnalyserNode | null;
  state: AvatarEvent;
}

const VoxWaveform: React.FC<Props> = ({ analyser, state }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!analyser || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    let lastTime = 0;
    const FPS = 30;  // Throttle for perf

    const draw = (time: number) => {
      if (time - lastTime > 1000 / FPS) {
        lastTime = time;
        analyser.getByteTimeDomainData(dataArray);

        ctx.fillStyle = 'rgb(0, 0, 0)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgb(255, 0, 0)';
        ctx.beginPath();

        const sliceWidth = canvas.width / bufferLength;
        let x = 0;
        for (let i = 0; i < bufferLength; i++) {
          const v = dataArray[i] / 128.0;
          const y = v * (canvas.height / 2);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
          x += sliceWidth;
        }
        ctx.lineTo(canvas.width, canvas.height / 2);
        ctx.stroke();
      }
      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);

    return () => cancelAnimationFrame(rafRef.current);
  }, [analyser, state]);

  return <canvas ref={canvasRef} width={400} height={200} style={{ border: '1px solid #fff' }} />;  // Added border for visibility
};

export default VoxWaveform;
