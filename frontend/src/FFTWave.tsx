import React, { useRef, useEffect } from 'react';

interface Props {
  rms: number;
}

const FFTWave: React.FC<Props> = ({ rms }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    ctx.moveTo(0, canvas.height / 2);
    for (let x = 0; x < canvas.width; x++) {
      const y = (Math.sin(x * 0.05) * rms * 100) + canvas.height / 2;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }, [rms]);

  return <canvas ref={canvasRef} width={400} height={200} />;
};

export default FFTWave;
