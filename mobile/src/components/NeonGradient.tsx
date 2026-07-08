import { StyleSheet, ViewStyle } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

interface NeonGradientProps {
  style?: ViewStyle;
  children?: React.ReactNode;
}

export function NeonGradient({ style, children }: NeonGradientProps) {
  const hue = useSharedValue(0);

  hue.value = withRepeat(withTiming(360, { duration: 8000 }), -1, false);

  const animatedStyle = useAnimatedStyle(() => ({
    backgroundColor: `hsla(${hue.value}, 70%, 60%, 0.1)`,
  }));

  return (
    <Animated.View style={[styles.container, animatedStyle, style]}>
      {children}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
