import { View, StyleSheet, ViewStyle } from 'react-native';
import { colors, borderRadius } from '../theme';

interface GlassCardProps {
  children: React.ReactNode;
  style?: ViewStyle;
}

export function GlassCard({ children, style }: GlassCardProps) {
  return (
    <View style={[styles.card, style]}>
      <View style={styles.inner}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.glass,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  inner: {
    padding: 16,
    backgroundColor: colors.glassDark,
  },
});
