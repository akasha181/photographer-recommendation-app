import { zodResolver } from '@hookform/resolvers/zod';
import React, { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { ApiError, api } from '../../../api/client';
import { ENDPOINTS } from '../../../api/config';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Screen } from '../../../components/layout/Screen';
import { colors, radius, spacing, typography } from '../../../theme';
import {
  forgotPasswordSchema,
  resetPasswordSchema,
  type ForgotPasswordForm,
  type ResetPasswordForm,
} from '../schemas';

interface Props {
  onGoLogin: () => void;
}

export function ForgotPasswordScreen({ onGoLogin }: Props) {
  const [stage, setStage] = useState<'request' | 'confirm' | 'done'>('request');
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const requestForm = useForm<ForgotPasswordForm>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });

  const confirmForm = useForm<ResetPasswordForm>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { email: '', code: '', new_password: '', new_password_confirm: '' },
  });

  const requestCode = async (values: ForgotPasswordForm) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const cleanEmail = values.email.trim().toLowerCase();
      await api.post(ENDPOINTS.auth.passwordReset, { email: cleanEmail });
      setEmail(cleanEmail);
      confirmForm.setValue('email', cleanEmail);
      confirmForm.setValue('code', '');
      setStage('confirm');
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : 'Could not send the code. Try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const confirmReset = async (values: ResetPasswordForm) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const payload = {
        email: (values.email || email).trim().toLowerCase(),
        code: String(values.code).trim(),
        new_password: values.new_password,
        new_password_confirm: values.new_password_confirm,
      };
      await api.post(ENDPOINTS.auth.passwordResetConfirm, payload);
      setStage('done');
    } catch (err) {
      if (err instanceof ApiError) {
        const fields = err.fieldErrors;
        let matched = false;
        for (const [field, message] of Object.entries(fields)) {
          if (field in values) {
            confirmForm.setError(field as keyof ResetPasswordForm, { message });
            matched = true;
          }
        }
        if (!matched) setFormError(err.message);
      } else {
        setFormError('Could not reset your password. Try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (stage === 'done') {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={styles.bigIcon}>✓</Text>
          <Text style={styles.title}>Password updated</Text>
          <Text style={styles.subtitle}>
            You can now sign in with your new password. All other devices have
            been signed out.
          </Text>
          <Button label="Back to sign in" onPress={onGoLogin} size="lg" />
        </View>
      </Screen>
    );
  }

  return (
    <Screen scroll>
      <Text style={styles.title}>
        {stage === 'request' ? 'Reset your password' : 'Enter the code'}
      </Text>
      <Text style={styles.subtitle}>
        {stage === 'request'
          ? "We'll email you a 6-digit code."
          : `We sent a code to ${email}. It expires in 15 minutes.`}
      </Text>

      {formError ? (
        <View style={styles.banner}>
          <Text style={styles.bannerText}>{formError}</Text>
        </View>
      ) : null}

      {stage === 'request' ? (
        <>
          <Controller
            control={requestForm.control}
            name="email"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="Email"
                icon="mail-outline"
                placeholder="you@example.com"
                value={value}
                onChangeText={onChange}
                onBlur={onBlur}
                error={requestForm.formState.errors.email?.message}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            )}
          />
          <Button
            label="Send code"
            onPress={requestForm.handleSubmit(requestCode)}
            loading={submitting}
            size="lg"
          />
        </>
      ) : (
        <>
          <Controller
            control={confirmForm.control}
            name="code"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="6-digit code"
                icon="keypad-outline"
                placeholder="000000"
                value={value}
                onChangeText={onChange}
                onBlur={onBlur}
                error={confirmForm.formState.errors.code?.message}
                keyboardType="number-pad"
                maxLength={6}
              />
            )}
          />
          <Controller
            control={confirmForm.control}
            name="new_password"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="New password"
                icon="lock-closed-outline"
                placeholder="At least 8 characters"
                value={value}
                onChangeText={onChange}
                onBlur={onBlur}
                error={confirmForm.formState.errors.new_password?.message}
                isPassword
              />
            )}
          />
          <Controller
            control={confirmForm.control}
            name="new_password_confirm"
            render={({ field: { onChange, onBlur, value } }) => (
              <Input
                label="Confirm new password"
                icon="lock-closed-outline"
                placeholder="Re-enter your password"
                value={value}
                onChangeText={onChange}
                onBlur={onBlur}
                error={confirmForm.formState.errors.new_password_confirm?.message}
                isPassword
              />
            )}
          />
          <Button
            label="Reset password"
            onPress={confirmForm.handleSubmit(confirmReset)}
            loading={submitting}
            size="lg"
          />

          <View style={styles.confirmActionsRow}>
            <TouchableOpacity
              onPress={() => requestCode({ email })}
              disabled={submitting}
              style={styles.actionBtn}
            >
              <Text style={styles.actionBtnText}>🔄 Resend code</Text>
            </TouchableOpacity>
            <Text style={styles.dividerDot}>•</Text>
            <TouchableOpacity
              onPress={() => {
                setStage('request');
                setFormError(null);
              }}
              style={styles.actionBtn}
            >
              <Text style={styles.actionBtnText}>✏️ Change email</Text>
            </TouchableOpacity>
          </View>
        </>
      )}

      <TouchableOpacity onPress={onGoLogin} style={styles.back}>
        <Text style={styles.backText}>Back to sign in</Text>
      </TouchableOpacity>
    </Screen>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  bigIcon: {
    fontSize: 44,
    color: colors.green,
    marginBottom: spacing.xl,
  },
  title: {
    ...typography.h1,
    color: colors.text,
    marginTop: spacing.xxxl,
    marginBottom: spacing.sm,
  },
  subtitle: { ...typography.body, color: colors.sub, marginBottom: spacing.xxl },
  banner: {
    backgroundColor: colors.redDim,
    borderColor: colors.red,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  bannerText: { ...typography.caption, color: colors.red },
  back: { alignSelf: 'center', marginTop: spacing.xxl, padding: spacing.sm },
  backText: { ...typography.caption, color: colors.gold, fontWeight: '600' },
  confirmActionsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  actionBtn: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  actionBtnText: {
    ...typography.caption,
    color: colors.text,
    fontWeight: '600',
  },
  dividerDot: {
    color: colors.dim,
  },
});
