import { zodResolver } from '@hookform/resolvers/zod';
import React, { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Screen } from '../../../components/layout/Screen';
import { useAuthStore } from '../../../store/authStore';
import { colors, radius, spacing, typography } from '../../../theme';
import { registerSchema, type RegisterForm } from '../schemas';

interface Props {
  onGoLogin: () => void;
}

const ROLES = [
  {
    value: 'BUYER' as const,
    title: "I'm hiring",
    detail: 'Find and book photographers',
    icon: '📷',
  },
  {
    value: 'PHOTOGRAPHER' as const,
    title: "I'm a photographer",
    detail: 'Get bookings and sell presets',
    icon: '🎯',
  },
];

export function RegisterScreen({ onGoLogin }: Props) {
  const register = useAuthStore((s) => s.register);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    setError,
    watch,
    setValue,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      full_name: '',
      email: '',
      phone: '',
      city: '',
      password: '',
      password_confirm: '',
      role: 'BUYER',
    },
  });

  const selectedRole = watch('role');

  const onSubmit = async (values: RegisterForm) => {
    setSubmitting(true);
    setFormError(null);
    try {
      await register(values);
    } catch (err) {
      if (err instanceof ApiError) {
        const fields = err.fieldErrors;
        let matched = false;
        for (const [field, message] of Object.entries(fields)) {
          if (field in values) {
            setError(field as keyof RegisterForm, { message });
            matched = true;
          }
        }
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
      <Text style={styles.title}>Create your account</Text>
      <Text style={styles.subtitle}>Takes less than a minute</Text>

      {/* Role is chosen at signup and cannot be changed later without an
          admin action — a single account is either a buyer or a seller, which
          keeps bookings, wallets and reviews unambiguous. */}
      <Text style={styles.sectionLabel}>I want to…</Text>
      <View style={styles.roleRow}>
        {ROLES.map((role) => {
          const active = selectedRole === role.value;
          return (
            <Pressable
              key={role.value}
              onPress={() => setValue('role', role.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected: active }}
              style={[styles.roleCard, active && styles.roleCardActive]}
            >
              <Text style={styles.roleIcon}>{role.icon}</Text>
              <Text style={[styles.roleTitle, active && styles.roleTitleActive]}>
                {role.title}
              </Text>
              <Text style={styles.roleDetail}>{role.detail}</Text>
            </Pressable>
          );
        })}
      </View>

      {formError ? (
        <View style={styles.banner} accessibilityLiveRegion="polite">
          <Text style={styles.bannerText}>{formError}</Text>
        </View>
      ) : null}

      <Controller
        control={control}
        name="full_name"
        render={({ field: { onChange, onBlur, value } }) => (
          <Input
            label="Full name"
            icon="person-outline"
            placeholder="Usama Shafiq"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.full_name?.message}
            autoComplete="name"
          />
        )}
      />

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
          />
        )}
      />

      <Controller
        control={control}
        name="phone"
        render={({ field: { onChange, onBlur, value } }) => (
          <Input
            label="Phone (optional)"
            icon="call-outline"
            placeholder="03001234567"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.phone?.message}
            keyboardType="phone-pad"
            hint="Pakistani mobile number"
          />
        )}
      />

      <Controller
        control={control}
        name="city"
        render={({ field: { onChange, onBlur, value } }) => (
          <Input
            label="City (optional)"
            icon="location-outline"
            placeholder="Islamabad"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.city?.message}
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
            placeholder="At least 8 characters"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.password?.message}
            isPassword
            autoComplete="new-password"
          />
        )}
      />

      <Controller
        control={control}
        name="password_confirm"
        render={({ field: { onChange, onBlur, value } }) => (
          <Input
            label="Confirm password"
            icon="lock-closed-outline"
            placeholder="Re-enter your password"
            value={value}
            onChangeText={onChange}
            onBlur={onBlur}
            error={errors.password_confirm?.message}
            isPassword
          />
        )}
      />

      <Button
        label="Create account"
        onPress={handleSubmit(onSubmit)}
        loading={submitting}
        size="lg"
      />

      <View style={styles.footer}>
        <Text style={styles.footerText}>Already have an account? </Text>
        <TouchableOpacity onPress={onGoLogin}>
          <Text style={styles.footerLink}>Sign in</Text>
        </TouchableOpacity>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { ...typography.h1, color: colors.text, marginTop: spacing.xxl },
  subtitle: { ...typography.body, color: colors.sub, marginBottom: spacing.xxl },
  sectionLabel: {
    ...typography.caption,
    color: colors.sub,
    fontWeight: '600',
    marginBottom: spacing.md,
  },
  roleRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.xxl },
  roleCard: {
    flex: 1,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  roleCardActive: { borderColor: colors.gold, backgroundColor: colors.cardHover },
  roleIcon: { fontSize: 24, marginBottom: spacing.sm },
  roleTitle: { ...typography.bodyBold, color: colors.text, marginBottom: spacing.xs },
  roleTitleActive: { color: colors.gold },
  roleDetail: { ...typography.tiny, color: colors.sub, lineHeight: 15 },
  banner: {
    backgroundColor: colors.redDim,
    borderColor: colors.red,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  bannerText: { ...typography.caption, color: colors.red },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: spacing.xxl,
    marginBottom: spacing.xxxl,
  },
  footerText: { ...typography.body, color: colors.sub },
  footerLink: { ...typography.body, color: colors.gold, fontWeight: '700' },
});
