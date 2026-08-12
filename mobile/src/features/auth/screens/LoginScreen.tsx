import { zodResolver } from '@hookform/resolvers/zod';
import React, { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Screen } from '../../../components/layout/Screen';
import { useAuthStore } from '../../../store/authStore';
import { colors, radius, spacing, typography } from '../../../theme';
import { loginSchema, type LoginForm } from '../schemas';

interface Props {
  onGoRegister: () => void;
  onGoForgot: () => void;
}

export function LoginScreen({ onGoRegister, onGoForgot }: Props) {
  const login = useAuthStore((s) => s.login);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: LoginForm) => {
    setSubmitting(true);
    setFormError(null);
    try {
      await login(values.email, values.password);
      // No navigation call here on purpose: RootNavigator watches
      // isAuthenticated and swaps the whole navigator. Navigating manually
      // as well would push a screen onto a tree that is about to unmount.
    } catch (err) {
      if (err instanceof ApiError) {
        // Map field errors back onto the form where possible…
        const fields = err.fieldErrors;
        let matched = false;
        for (const [field, message] of Object.entries(fields)) {
          if (field === 'email' || field === 'password') {
            setError(field, { message });
            matched = true;
          }
        }
        // …otherwise show it as a banner (blocked account, lockout, etc).
        if (!matched) setFormError(err.message);
      } else {
        setFormError('Something went wrong. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Screen scroll>
      <View style={styles.header}>
        <View style={styles.logoMark}>
          <Text style={styles.logoGlyph}>S</Text>
        </View>
        <Text style={styles.title}>Welcome back</Text>
        <Text style={styles.subtitle}>
          Sign in to book Pakistan's best photographers
        </Text>
      </View>

      {formError ? (
        <View style={styles.banner} accessibilityLiveRegion="polite">
          <Text style={styles.bannerText}>{formError}</Text>
        </View>
      ) : null}

      <Controller
        control={control}
        name="email"
        render={({ field: { onChange, onBlur, value } }) => (
          <Input
            label="Email"
            icon="mail-outline"
            placeholder="you@example.com"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.email?.message}
            keyboardType="email-address"
            autoCapitalize="none"
            autoComplete="email"
            textContentType="emailAddress"
          />
        )}
      />

      <Controller
        control={control}
        name="password"
        render={({ field: { onChange, onBlur, value } }) => (
          <Input
            label="Password"
            icon="lock-closed-outline"
            placeholder="Your password"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.password?.message}
            isPassword
            autoComplete="current-password"
            textContentType="password"
            onSubmitEditing={handleSubmit(onSubmit)}
            returnKeyType="go"
          />
        )}
      />

      <TouchableOpacity onPress={onGoForgot} style={styles.forgot}>
        <Text style={styles.forgotText}>Forgot password?</Text>
      </TouchableOpacity>

      <Button
        label="Sign in"
        onPress={handleSubmit(onSubmit)}
        loading={submitting}
        size="lg"
      />

      <View style={styles.footer}>
        <Text style={styles.footerText}>New to SnapSphere? </Text>
        <TouchableOpacity onPress={onGoRegister}>
          <Text style={styles.footerLink}>Create an account</Text>
        </TouchableOpacity>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: 'center', marginTop: spacing.huge, marginBottom: spacing.xxxl },
  logoMark: {
    width: 64,
    height: 64,
    borderRadius: radius.xl,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xl,
  },
  logoGlyph: { ...typography.display, color: colors.bg },
  title: { ...typography.h1, color: colors.text, marginBottom: spacing.sm },
  subtitle: { ...typography.body, color: colors.sub, textAlign: 'center' },
  banner: {
    backgroundColor: colors.redDim,
    borderColor: colors.red,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  bannerText: { ...typography.caption, color: colors.red },
  forgot: { alignSelf: 'flex-end', marginBottom: spacing.xl, padding: spacing.xs },
  forgotText: { ...typography.caption, color: colors.gold, fontWeight: '600' },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: spacing.xxl,
  },
  footerText: { ...typography.body, color: colors.sub },
  footerLink: { ...typography.body, color: colors.gold, fontWeight: '700' },
});
