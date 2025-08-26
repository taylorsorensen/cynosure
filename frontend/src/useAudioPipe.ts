import { useState, useEffect } from 'react';

const useAudioPipe = () => {
  const [rms, setRms] = useState(0);

  useEffect(() => {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.fftSize);

      const update = () => {
        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const a = dataArray[i] / 128 - 1;
          sum += a * a;
        }
        setRms(Math.sqrt(sum / dataArray.length));
        requestAnimationFrame(update);
      };
      update();
    });
  }, []);

  return { rms };
};

export default useAudioPipe;
