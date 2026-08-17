import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TouchableOpacity,
  View,
} from 'react-native';

import { colors, radius, spacing, typography, MIN_TOUCH_SIZE } from '../../theme';

interface Props extends TextInputProps {
  label?: string;
  error?: string;
  hint?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  isPassword?: boolean;
}

export function Input({
  label,
  error,
  hint,
  icon,
  isPassword = false,
  ...rest
}: Props) {
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(isPassword);

  /**
   * A password field must never be autocapitalised, autocorrected or
   * spell-checked.
   *
   * WHY THIS IS NOT OPTIONAL
   * ------------------------
   * `autoCapitalize` defaults to `'sentences'`. `secureTextEntry` suppresses it
   * on most keyboards — but the reveal toggle below sets `secureTextEntry` to
   * false, and from that moment this is a plain text field with sentence
   * capitalisation and predictive text switched on. Typing "buyer12345" then
   * submits "Buyer12345", the server correctly rejects it, and the user is told
   * "No active account found with the given credentials" while looking at a
   * password that appears exactly right.
   *
   * Declared BEFORE the spread so a caller can still override it deliberately.
   */
  const passwordSafeInput = isPassword
    ? { autoCapitalize: 'none' as const, autoCorrect: false, spellCheck: false }
    : {};

  return (
    <View style={styles.wrapper}>
      {label ? <Text style={styles.label}>{label}</Text> : null}

      <View
        style={[
          styles.field,
          focused && styles.fieldFocused,
          !!error && styles.fieldError,
        ]}
      >
        {icon ? (
          <Ionicons
            name={icon}
            size={18}
            color={error ? colors.red : focused ? colors.gold : colors.dim}
            style={styles.icon}
          />
        ) : null}

        <TextInput
          {...passwordSafeInput}
          {...rest}
          style={styles.input}
          placeholderTextColor={colors.dim}
          secureTextEntry={hidden}
          onFocus={(e) => {
            setFocused(true);
            rest.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            rest.onBlur?.(e);
          }}
          accessibilityLabel={label ?? rest.placeholder}
          // Announce the error to screen readers, not just visually.
          accessibilityHint={error ?? hint}
        />

        {isPassword ? (
          <TouchableOpacity
            onPress={() => setHidden((v) => !v)}
            style={styles.reveal}
            accessibilityRole="button"
            accessibilityLabel={hidden ? 'Show password' : 'Hide password'}
          >
            <Ionicons
              name={hidden ? 'eye-outline' : 'eye-off-outline'}
              size={19}
              color={colors.sub}
            />
          </TouchableOpacity>
        ) : null}
      </View>

      {error ? (
        <Text style={styles.error}>{error}</Text>
      ) : hint ? (
        <Text style={styles.hint}>{hint}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { marginBottom: spacing.lg },
  label: {
    ...typography.caption,
    color: colors.sub,
    marginBottom: spacing.sm,
    fontWeight: '600',
  },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: MIN_TOUCH_SIZE,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
  },
  fieldFocused: { borderColor: colors.gold, backgroundColor: colors.cardHover },
  fieldError: { borderColor: colors.red },
  icon: { marginRight: spacing.sm },
  input: {
    flex: 1,
    ...typography.body,
    color: colors.text,
    paddingVertical: spacing.md,
  },
  reveal: { padding: spacing.sm },
  error: { ...typography.caption, color: colors.red, marginTop: spacing.xs },
  hint: { ...typography.caption, color: colors.dim, marginTop: spacing.xs },
});
