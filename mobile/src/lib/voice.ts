import { useRef, useState, useCallback } from 'react';
import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system';
import * as Speech from 'expo-speech';
import { api } from './api';

export function useVoice() {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  async function startRecording() {
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) return;
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync({
        ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
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
      setRecording(rec);
      setIsRecording(true);
    } catch { }
  }

  async function stopRecording(): Promise<string | null> {
    if (!recording) return null;
    try {
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);
      setIsRecording(false);
      return uri;
    } catch {
      setRecording(null);
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
    setIsSpeaking(true);
    Speech.speak(text, {
      language: 'en',
      rate: 0.85,
      onDone: () => setIsSpeaking(false),
      onError: () => setIsSpeaking(false),
    });
  }

  function stopSpeaking() {
    Speech.stop();
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
