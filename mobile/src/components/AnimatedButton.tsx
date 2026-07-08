import { TouchableOpacity, Text, StyleSheet, ViewStyle } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { colors, borderRadius, typography } from '../theme';

const AnimatedTouchable = Animated.createAnimatedComponent(TouchableOpacity);

interface AnimatedButtonProps {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost';
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
}

export function AnimatedButton({
  title,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  style,
}: AnimatedButtonProps) {
  const scale = useSharedValue(1);
  const glow = useSharedValue(0.5);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: disabled ? 0.5 : 1,
  }));

  const glowStyle = useAnimatedStyle(() => ({
    opacity: glow.value,
  }));

  function handlePressIn() {
    scale.value = withSpring(0.97);
    glow.value = withTiming(1, { duration: 200 });
  }

  function handlePressOut() {
    scale.value = withSpring(1);
    glow.value = withTiming(0.5, { duration: 200 });
  }

  const isPrimary = variant === 'primary';
  const isSecondary = variant === 'secondary';

  return (
    <AnimatedTouchable
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      disabled={disabled || loading}
      style={[
        styles.base,
        isPrimary && styles.primary,
        isSecondary && styles.secondary,
        variant === 'ghost' && styles.ghost,
        animatedStyle,
        style,
      ]}
      activeOpacity={0.9}
    >
      {isPrimary && <Animated.View style={[styles.glow, glowStyle]} />}
      <Text
        style={[
          typography.button,
          isPrimary && styles.primaryText,
          isSecondary && styles.secondaryText,
          variant === 'ghost' && styles.ghostText,
        ]}
      >
        {loading ? 'Please wait...' : title}
      </Text>
    </AnimatedTouchable>
  );
}

const styles = StyleSheet.create({
  base: {
    paddingVertical: 16,
    paddingHorizontal: 24,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    position: 'relative',
    overflow: 'hidden',
  },
  primary: {
    backgroundColor: colors.primary,
  },
  secondary: {
    backgroundColor: colors.surfaceLight,
    borderWidth: 1,
    borderColor: colors.border,
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  glow: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
  },
  primaryText: {
    color: colors.bg,
  },
  secondaryText: {
    color: colors.text,
  },
  ghostText: {
    color: colors.primary,
  },
});
