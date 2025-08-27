import React, { useEffect, useState } from 'react';
import { AvatarEvent } from './types';

interface Props {
  event: AvatarEvent;
}

const Avatar: React.FC<Props> = ({ event }) => {
  const [scale, setScale] = useState(1);
  let emoji = '😊';
  switch (event) {
    case 'idle': emoji = '😌'; break;  // Added for variety
    case 'listening': emoji = '👂'; break;
    case 'thinking': emoji = '🤔'; break;
    case 'speaking': emoji = '🗣️'; break;
    case 'error': emoji = '😕'; break;
  }

  useEffect(() => {
    if (event === 'speaking' || event === 'listening') {
      const interval = setInterval(() => {
        setScale(1 + Math.random() * 0.1);
      }, 100);
      return () => clearInterval(interval);
    }
    setScale(1);
  }, [event]);

  return (
    <div style={{ fontSize: '100px', transition: 'transform 0.1s ease-in-out', transform: `scale(${scale})` }}>
      {emoji}
    </div>
  );
};

export default Avatar;
