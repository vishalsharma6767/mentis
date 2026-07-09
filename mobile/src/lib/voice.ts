import { useState, useRef, useCallback, useEffect } from 'react';
import { Platform } from 'react-native';
import { api } from './api';

const isWeb = Platform.OS === 'web';

function noop() {}

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcript, setTranscript] = useState('');
  const recognitionRef = useRef<any>(null);
  const finalTranscriptRef = useRef('');
  const silenceTimerRef = useRef<any>(null);
  const onTranscriptReadyRef = useRef<((text: string) => void) | null>(null);

  // Web SpeechRecognition setup
  useEffect(() => {
    if (!isWeb) return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event: any) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }
      if (final) {
        finalTranscriptRef.current += ' ' + final;
        setTranscript(finalTranscriptRef.current.trim());
      }
      if (interim) {
        setTranscript((finalTranscriptRef.current + ' ' + interim).trim());
      }
      // Reset silence timer
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = setTimeout(() => {
        const text = finalTranscriptRef.current.trim();
        if (text && onTranscriptReadyRef.current) {
          onTranscriptReadyRef.current(text);
          finalTranscriptRef.current = '';
          setTranscript('');
        }
      }, 1200);
    };

    recognition.onerror = noop;
    recognitionRef.current = recognition;

    return () => {
      try { recognition.stop(); } catch {}
    };
  }, []);

  const startListening = useCallback((onReady: (text: string) => void) => {
    onTranscriptReadyRef.current = onReady;
    if (isWeb) {
      try {
        recognitionRef.current?.start();
        setIsRecording(true);
      } catch {
        try {
          recognitionRef.current?.stop();
          setTimeout(() => recognitionRef.current?.start(), 100);
          setIsRecording(true);
        } catch {}
      }
    }
  }, []);

  const stopListening = useCallback(() => {
    if (isWeb) {
      try { recognitionRef.current?.stop(); } catch {}
    }
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    setIsRecording(false);
    finalTranscriptRef.current = '';
    setTranscript('');
    onTranscriptReadyRef.current = null;
  }, []);

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

  async function findVoice(lang: string): Promise<SpeechSynthesisVoice | undefined> {
    for (let i = 0; i < 10; i++) {
      const voices = speechSynthesis.getVoices();
      if (voices.length > 0) return voices.find(v => v.lang.startsWith(lang));
      await new Promise(r => setTimeout(r, 200));
    }
    return undefined;
  }

  async function speakText(text: string) {
    if (isWeb) {
      if ('speechSynthesis' in window) {
        setIsSpeaking(true);
        const hiVoice = await findVoice('hi');
        return new Promise<void>((resolve) => {
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.rate = 0.76;
          utterance.pitch = 1.05;
          if (hiVoice) { utterance.voice = hiVoice; utterance.lang = 'hi-IN'; }
          else { utterance.lang = 'en-IN'; }
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
        language: 'hi-IN',
        rate: 0.76,
        onDone: () => setIsSpeaking(false),
        onError: () => setIsSpeaking(false),
      });
    } catch {
      try {
        setIsSpeaking(true);
        const mod = await import('expo-speech');
        mod.speak(text, {
          language: 'en-IN',
          rate: 0.76,
          onDone: () => setIsSpeaking(false),
          onError: () => setIsSpeaking(false),
        });
      } catch {
        setIsSpeaking(false);
      }
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
    startListening,
    stopListening,
    transcript,
    isRecording,
    isSpeaking,
  };
}
