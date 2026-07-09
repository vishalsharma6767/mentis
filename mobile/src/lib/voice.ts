import { useState } from 'react';
import { Platform } from 'react-native';
import { api } from './api';

const isWeb = Platform.OS === 'web';

function noop() {}

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  async function startRecording() {
    if (isWeb) return;
    try {
      const { Audio } = await import('expo-av');
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) return;
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      const rec = new Audio.Recording();
      const presets = Audio.RecordingOptionsPresets || { HIGH_QUALITY: {} };
      await rec.prepareToRecordAsync({
        ...presets.HIGH_QUALITY,
        android: {
          extension: '.m4a',
          outputFormat: Audio.AndroidOutputFormat.MPEG_4,
          audioEncoder: Audio.AndroidAudioEncoder.AAC,
          sampleRate: 44100,
          numberOfChannels: 1,
          bitRate: 128000,
        },
        ios: {
          extension: '.m4a',
          outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
          audioQuality: Audio.IOSAudioQuality.MAX,
          sampleRate: 44100,
          numberOfChannels: 1,
          bitRate: 128000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
      });
      await rec.startAsync();
      (window as any).__mentis_recording = rec;
      setIsRecording(true);
    } catch {}
  }

  async function stopRecording(): Promise<string | null> {
    if (isWeb) return null;
    try {
      const { Audio } = await import('expo-av');
      const rec: any = (window as any).__mentis_recording;
      if (!rec) return null;
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      (window as any).__mentis_recording = null;
      setIsRecording(false);
      return uri;
    } catch {
      setIsRecording(false);
      return null;
    }
  }

  async function transcribeAudio(uri: string): Promise<string | null> {
    try {
      const result = await api.transcribeAudio(uri);
      return result.text;
    } catch {
      return null;
    }
  }

  async function speakText(text: string) {
    if (isWeb) {
      if ('speechSynthesis' in window) {
        setIsSpeaking(true);
        return new Promise<void>((resolve) => {
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.rate = 0.85;
          utterance.onend = () => { setIsSpeaking(false); resolve(); };
          utterance.onerror = () => { setIsSpeaking(false); resolve(); };
          speechSynthesis.speak(utterance);
        });
      }
      return;
    }
    try {
      setIsSpeaking(true);
      const mod = await import('expo-speech');
      mod.speak(text, {
        language: 'en',
        rate: 0.85,
        onDone: () => setIsSpeaking(false),
        onError: () => setIsSpeaking(false),
      });
    } catch {
      setIsSpeaking(false);
    }
  }

  function stopSpeaking() {
    if (isWeb && 'speechSynthesis' in window) {
      speechSynthesis.cancel();
    } else {
      import('expo-speech').then((mod) => mod.stop()).catch(noop);
    }
    setIsSpeaking(false);
  }

  return {
    startRecording,
    stopRecording,
    transcribeAudio,
    speakText,
    stopSpeaking,
    isRecording,
    isSpeaking,
  };
}
