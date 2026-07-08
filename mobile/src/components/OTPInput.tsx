import { useRef, useState, useEffect } from 'react';
import {
  View,
  TextInput,
  StyleSheet,
  Platform,
  Text,
  TouchableOpacity,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { colors, borderRadius, spacing } from '../theme';
import { AnimatedButton } from './AnimatedButton';

const OTP_LENGTH = 6;

interface OTPInputProps {
  onComplete: (code: string) => void;
  onResend: () => void;
  error?: boolean;
  loading?: boolean;
}

function OTPBox({ value, focused, error }: { value: string; focused: boolean; error: boolean }) {
  const scale = useSharedValue(1);
  const borderColor = useSharedValue(0);

  useEffect(() => {
    scale.value = withSpring(focused ? 1.05 : 1);
    borderColor.value = withTiming(focused ? 1 : 0, { duration: 200 });
  }, [focused]);

  useEffect(() => {
    if (error) {
      scale.value = withSequence(
        withTiming(1.1, { duration: 50 }),
        withTiming(0.95, { duration: 50 }),
        withTiming(1.05, { duration: 50 }),
        withTiming(0.95, { duration: 50 }),
        withSpring(1, { duration: 200 }),
      );
    }
  }, [error]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    borderColor: borderColor.value === 1 ? colors.primary : colors.border,
  }));

  return (
    <Animated.View
      style={[
        styles.box,
        animatedStyle,
        error && styles.boxError,
        focused && styles.boxFocused,
      ]}
    >
      <Text style={[styles.boxText, !!value && styles.boxTextFilled]}>
        {value}
      </Text>
    </Animated.View>
  );
}

export function OTPInput({ onComplete, onResend, error, loading }: OTPInputProps) {
  const [code, setCode] = useState<string[]>(Array(OTP_LENGTH).fill(''));
  const [focusedIndex, setFocusedIndex] = useState(0);
  const inputRef = useRef<TextInput>(null);
  const [shakeError, setShakeError] = useState(false);
  const [timer, setTimer] = useState(30);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (timer > 0) {
      timerRef.current = setInterval(() => setTimer((t) => t - 1), 1000);
      return () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      };
    }
  }, []);

  function startResendTimer() {
    setTimer(30);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    timerRef.current = setInterval(() => setTimer((t) => t - 1), 1000);
  }

  function handleChangeText(text: string) {
    const digits = text.replace(/[^0-9]/g, '').split('');
    const newCode = Array(OTP_LENGTH).fill('');

    for (let i = 0; i < Math.min(digits.length, OTP_LENGTH); i++) {
      newCode[i] = digits[i];
    }

    setCode(newCode);

    if (digits.length < OTP_LENGTH) {
      setFocusedIndex(digits.length);
    } else {
      setFocusedIndex(OTP_LENGTH - 1);
    }
  }

  function handleSubmit() {
    const fullCode = code.join('');
    if (fullCode.length !== OTP_LENGTH || loading) return;
    onComplete(fullCode);
  }

  function handleResendPress() {
    setCode(Array(OTP_LENGTH).fill(''));
    setFocusedIndex(0);
    setShakeError(false);
    startResendTimer();
    onResend();
  }

  useEffect(() => {
    if (error) {
      setShakeError(true);
      setCode(Array(OTP_LENGTH).fill(''));
      setFocusedIndex(0);
      const t = setTimeout(() => setShakeError(false), 600);
      return () => clearTimeout(t);
    }
  }, [error]);

  const isComplete = code.join('').length === OTP_LENGTH;

  return (
    <View style={styles.container}>
      <TouchableOpacity activeOpacity={1} onPress={() => inputRef.current?.focus()} style={styles.boxesWrapper}>
        <View style={styles.boxes}>
          {code.map((digit, index) => (
            <OTPBox
              key={index}
              value={digit}
              focused={focusedIndex === index && !shakeError}
              error={shakeError}
            />
          ))}
        </View>
      </TouchableOpacity>

      {Platform.OS === 'web' ? (
        <TextInput
          ref={inputRef}
          style={styles.webInput}
          keyboardType="numeric"
          inputMode="numeric"
          maxLength={OTP_LENGTH}
          value={code.join('')}
          onChangeText={handleChangeText}
          autoFocus
          onKeyPress={({ nativeEvent }) => {
            if (nativeEvent.key === 'Enter') handleSubmit();
          }}
        />
      ) : (
        <TextInput
          ref={inputRef}
          style={styles.hiddenInput}
          keyboardType="number-pad"
          maxLength={OTP_LENGTH}
          value={code.join('')}
          onChangeText={handleChangeText}
          autoFocus
        />
      )}

      <AnimatedButton
        title="Verify Code"
        onPress={handleSubmit}
        disabled={!isComplete || loading}
        loading={loading}
        style={styles.submitButton}
      />

      <View style={styles.resendRow}>
        <Text style={styles.resendLabel}>Didn't receive the code? </Text>
        <TouchableOpacity onPress={handleResendPress} disabled={timer > 0}>
          <Text style={[styles.resendLink, timer > 0 && styles.resendDisabled]}>
            {timer > 0 ? `Resend in ${timer}s` : 'Resend'}
          </Text>
        </TouchableOpacity>
      </View>

      {error && (
        <Text style={styles.errorText}>
          Invalid code. Check your email and try again.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: spacing.lg,
  },
  boxesWrapper: {
    width: '100%',
  },
  boxes: {
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'center',
  },
  box: {
    width: 48,
    height: 56,
    borderRadius: borderRadius.md,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  boxFocused: {
    borderColor: colors.primary,
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 4,
  },
  boxError: {
    borderColor: colors.error,
  },
  boxText: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.textTertiary,
  },
  boxTextFilled: {
    color: colors.text,
  },
  hiddenInput: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
  },
  webInput: {
    position: 'absolute',
    width: '100%',
    height: 1,
    opacity: 0.01,
  },
  submitButton: {
    width: '100%',
    marginTop: spacing.sm,
  },
  resendRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  resendLabel: {
    color: colors.textSecondary,
    fontSize: 14,
  },
  resendLink: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: '700',
  },
  resendDisabled: {
    color: colors.textTertiary,
  },
  errorText: {
    color: colors.error,
    fontSize: 14,
    textAlign: 'center',
  },
});
