import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from 'react-native';

import { colors, radius, spacing, typography, MIN_TOUCH_SIZE } from '../../theme';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface Props {
  label: string;
  onPress: () => void;
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  icon?: React.ReactNode;
  style?: ViewStyle;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  fullWidth = true,
  icon,
  style,
}: Props) {
  // A loading button must also be disabled. Otherwise a double-tap fires the
  // mutation twice — which on a booking screen means two booking requests.
  const isInactive = disabled || loading;

  return (
    <Pressable
      onPress={onPress}
      disabled={isInactive}
      accessibilityRole="button"
      accessibilityState={{ disabled: isInactive, busy: loading }}
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.base,
        sizeStyles[size],
        variantStyles[variant],
        fullWidth && styles.fullWidth,
        pressed && !isInactive && styles.pressed,
        isInactive && styles.inactive,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator
          size="small"
          color={variant === 'primary' ? colors.bg : colors.text}
        />
      ) : (
        <View style={styles.content}>
          {icon}
          <Text style={[styles.label, labelStyles[variant], labelSizes[size]]}>
            {label}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: MIN_TOUCH_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
  },
  fullWidth: { alignSelf: 'stretch' },
  content: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  label: { textAlign: 'center' },
  pressed: { opacity: 0.75, transform: [{ scale: 0.985 }] },
  inactive: { opacity: 0.45 },
});

const sizeStyles: Record<Size, ViewStyle> = {
  sm: { paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, minHeight: 38 },
  md: { paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  lg: { paddingVertical: spacing.lg, paddingHorizontal: spacing.xxl },
};

const labelSizes = {
  sm: typography.caption,
  md: typography.bodyBold,
  lg: typography.h3,
};

const variantStyles: Record<Variant, ViewStyle> = {
  primary: { backgroundColor: colors.gold, borderColor: colors.gold },
  secondary: { backgroundColor: colors.card, borderColor: colors.borderMid },
  ghost: { backgroundColor: colors.transparent, borderColor: colors.transparent },
  danger: { backgroundColor: colors.redDim, borderColor: colors.red },
};

const labelStyles = {
  primary: { color: colors.bg, fontWeight: '700' as const },
  secondary: { color: colors.text, fontWeight: '600' as const },
  ghost: { color: colors.gold, fontWeight: '600' as const },
  danger: { color: colors.red, fontWeight: '600' as const },
};
