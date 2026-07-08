import { useRef, useState, useEffect } from 'react';
import {
  View,
  TextInput,
  StyleSheet,
  Keyboard,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import { colors, borderRadius, spacing } from '../theme';
import { AnimatedButton } from './AnimatedButton';

const OTP_LENGTH = 6;

interface OTPInputProps {
  onComplete: (code: string) => void;
  onResend: () => void;
  error?: boolean;
}

function OTPBox({
  index,
  value,
  focused,
  error,
}: {
  index: number;
  value: string;
  focused: boolean;
  error: boolean;
}) {
  const scale = useSharedValue(1);
  const borderColor = useSharedValue(0);

  useEffect(() => {
    if (focused) {
      scale.value = withSpring(1.05);
      borderColor.value = withTiming(1, { duration: 200 });
    } else {
      scale.value = withSpring(1);
      borderColor.value = withTiming(0, { duration: 200 });
    }
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
      <Animated.Text style={[styles.boxText, !!value && styles.boxTextFilled]}>
        {value}
      </Animated.Text>
    </Animated.View>
  );
}

export function OTPInput({ onComplete, onResend, error }: OTPInputProps) {
  const [code, setCode] = useState<string[]>(Array(OTP_LENGTH).fill(''));
  const [focusedIndex, setFocusedIndex] = useState(0);
  const inputRef = useRef<TextInput>(null);
  const [shakeError, setShakeError] = useState(false);

  function handleKeyPress(text: string) {
    const digits = text.replace(/[^0-9]/g, '').split('');
    const newCode = [...code];

    for (let i = 0; i < OTP_LENGTH; i++) {
      newCode[i] = digits[i] ?? '';
    }

    setCode(newCode);

    const filledCount = digits.length;
    if (filledCount < OTP_LENGTH) {
      setFocusedIndex(filledCount);
    } else {
      setFocusedIndex(OTP_LENGTH - 1);
      const fullCode = newCode.join('');
      if (fullCode.length === OTP_LENGTH) {
        Keyboard.dismiss();
        onComplete(fullCode);
      }
    }
  }

  useEffect(() => {
    if (error) {
      setShakeError(true);
      setCode(Array(OTP_LENGTH).fill(''));
      setFocusedIndex(0);
      const timer = setTimeout(() => setShakeError(false), 600);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return (
    <View style={styles.container}>
      <View style={styles.boxes}>
        {code.map((digit, index) => (
          <OTPBox
            key={index}
            index={index}
            value={digit}
            focused={focusedIndex === index}
            error={shakeError}
          />
        ))}
      </View>
      <TextInput
        ref={inputRef}
        style={styles.hiddenInput}
        keyboardType="number-pad"
        maxLength={OTP_LENGTH}
        value={code.join('')}
        onChangeText={handleKeyPress}
        autoFocus
      />
      <AnimatedButton
        title="Resend Code"
        variant="ghost"
        onPress={onResend}
        style={styles.resendButton}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: spacing.lg,
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
  resendButton: {
    marginTop: spacing.sm,
  },
});
