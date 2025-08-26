import React, { useEffect, useState, useRef, useCallback } from 'react';
import VoxWaveform from './VoxWaveform';
import Avatar from './Avatar';
import { AvatarEvent } from './types';

const App: React.FC = () => {
  const [state, setState] = useState<AvatarEvent>('idle');
  const [response, setResponse] = useState('');

  // Audio context and WebSocket refs
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // --- Audio Playback Queue ---
  const audioQueueRef = useRef<AudioBufferSourceNode[]>([]);
  const isPlayingRef = useRef<boolean>(false);

  const playNextInQueue = useCallback(() => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) {
      return;
    }

    isPlayingRef.current = true;
    const sourceNode = audioQueueRef.current.shift();

    if (sourceNode && audioContextRef.current) {
      sourceNode.onended = () => {
        isPlayingRef.current = false;
        playNextInQueue();
      };
      sourceNode.connect(analyserRef.current!);
      sourceNode.connect(audioContextRef.current.destination);
      sourceNode.start();
    } else {
      isPlayingRef.current = false;
    }
  }, []);


  useEffect(() => {
    audioContextRef.current = new AudioContext();
    analyserRef.current = audioContextRef.current.createAnalyser();
    analyserRef.current.fftSize = 2048;

    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      sourceRef.current = audioContextRef.current!.createMediaStreamSource(stream);
      sourceRef.current.connect(analyserRef.current!);
    });

    wsRef.current = new WebSocket('ws://localhost:8000');
    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.state) {
        setState(data.state);
      }
      if (data.data?.response) {
        setResponse(prev => prev + data.data.response);
      }
      if (data.data?.tool_result) {
        setResponse(prev => prev + '\n' + data.data.tool_result);
      }

      if (data.audio_chunk) {
        if (!audioContextRef.current) return;
        const chunk = new Float32Array(data.audio_chunk);
        const buffer = audioContextRef.current.createBuffer(1, chunk.length, 24000);
        buffer.copyToChannel(chunk, 0);

        const sourceNode = audioContextRef.current.createBufferSource();
        sourceNode.buffer = buffer;

        audioQueueRef.current.push(sourceNode);
        playNextInQueue();
      }
    };

    wsRef.current.onopen = () => {
      setResponse('');
      wsRef.current!.send(JSON.stringify({ action: 'start' }));
    };

    wsRef.current.onclose = () => {
        setState('error');
    };

    return () => wsRef.current?.close();
  }, [playNextInQueue]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      textAlign: 'center'
    }}>
      <Avatar event={state} />
      <VoxWaveform analyser={analyserRef.current} state={state} />
      <p style={{ whiteSpace: 'pre-wrap' }}>{response}</p>
    </div>
  );
};

export default App;
