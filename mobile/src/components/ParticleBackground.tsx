import { useEffect } from 'react';
import { StyleSheet, Dimensions } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withDelay,
} from 'react-native-reanimated';
import { colors } from '../theme';

const PARTICLE_COUNT = 30;
const { width, height } = Dimensions.get('window');

interface ParticleData {
  x: number;
  y: number;
  size: number;
  delay: number;
  duration: number;
}

const particles: ParticleData[] = Array.from({ length: PARTICLE_COUNT }, () => ({
  x: Math.random() * width,
  y: Math.random() * height,
  size: 2 + Math.random() * 3,
  delay: Math.random() * 5000,
  duration: 6000 + Math.random() * 4000,
}));

function Particle({ data }: { data: ParticleData }) {
  const translateY = useSharedValue(0);
  const opacity = useSharedValue(0);

  useEffect(() => {
    opacity.value = withDelay(
      data.delay,
      withRepeat(
        withTiming(0.4, { duration: data.duration }),
        -1,
        true,
      ),
    );
    translateY.value = withDelay(
      data.delay,
      withRepeat(
        withTiming(-data.y - 50, { duration: data.duration }),
        -1,
        true,
      ),
    );
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
    opacity: opacity.value,
  }));

  return (
    <Animated.View
      style={[
        styles.particle,
        {
          width: data.size,
          height: data.size,
          left: data.x,
          top: data.y + 100,
          borderRadius: data.size / 2,
        },
        animatedStyle,
      ]}
    />
  );
}

export function ParticleBackground() {
  return (
    <Animated.View style={styles.container}>
      {particles.map((data, i) => (
        <Particle key={i} data={data} />
      ))}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFill,
    pointerEvents: 'none',
  },
  particle: {
    position: 'absolute',
    backgroundColor: colors.primary,
  },
});
