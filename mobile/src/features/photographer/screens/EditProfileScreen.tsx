import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { useAuthStore } from '../../../store/authStore';
import { colors, radius, spacing, typography } from '../../../theme';
import type { PhotographerSelfProfile } from '../../../types/models';
import { useMyProfile, useUpdateProfile } from '../../shop/hooks/useShop';

/**
 * The photographer's public listing, edited by its owner.
 *
 * WHAT IS NOT ON THIS FORM
 * ------------------------
 * Approval, verification, featured status, ratings and every booking counter.
 * The write serializer omits them entirely, so sending them changes nothing —
 * but leaving them off the form is what stops a photographer expecting to
 * verify themselves and finding the toggle silently ignored.
 *
 * Name, phone and city belong to the account, not the listing, and live at
 * /auth/me/. Duplicating them here would give two screens that can disagree.
 */
export function EditProfileScreen({ onBack }: { onBack: () => void }) {
  const user = useAuthStore((s) => s.user);
  const profile = useMyProfile();
  const updateProfile = useUpdateProfile();

  const [form, setForm] = useState<Record<string, string> | null>(null);

  if (profile.isLoading) return <LoadingState label="Loading your profile…" />;
  if (profile.isError || !profile.data) {
    return (
      <ErrorState
        message={(profile.error as ApiError)?.message}
        onRetry={() => profile.refetch()}
      />
    );
  }

  const data = profile.data as PhotographerSelfProfile;
  const values = form ?? {
    business_name: data.business_name ?? '',
    tagline: data.tagline ?? '',
    bio: data.bio ?? '',
    years_experience: String(data.years_experience ?? 0),
    base_price: String(Math.round(Number(data.base_price ?? 0))),
    equipment: data.equipment ?? '',
    languages: data.languages ?? '',
    website: data.website ?? '',
    instagram: data.instagram ?? '',
    service_radius_km: String(data.service_radius_km ?? 50),
  };

  const set = (key: string, value: string) => setForm({ ...values, [key]: value });

  const save = () => {
    if (values.bio.trim() && values.bio.trim().length < 50) {
      Alert.alert(
        'Bio is too short',
        'A bio needs at least 50 characters to be useful to buyers — say what you shoot and how you work.',
      );
      return;
    }

    updateProfile.mutate(
      {
        business_name: values.business_name.trim(),
        tagline: values.tagline.trim(),
        bio: values.bio.trim(),
        years_experience: Number(values.years_experience) || 0,
        equipment: values.equipment.trim(),
        languages: values.languages.trim(),
        website: values.website.trim(),
        instagram: values.instagram.trim().replace(/^@/, ''),
        service_radius_km: Number(values.service_radius_km) || 50,
      },
      {
        onSuccess: () => {
          setForm(null);
          Alert.alert('Saved', 'Your profile is updated.');
        },
        onError: (error) =>
          Alert.alert('Could not save', (error as ApiError).message),
      },
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>Edit profile</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {!data.is_approved ? (
          <View style={styles.notice}>
            <Ionicons name="hourglass-outline" size={16} color={colors.amber} />
            <Text style={styles.noticeText}>
              {data.rejection_reason ||
                'Your profile is awaiting admin approval. Completing it — bio, services, five portfolio photos — is what gets it reviewed.'}
            </Text>
          </View>
        ) : null}

        <Text style={styles.section}>Public identity</Text>
        <Input
          label="Business name"
          placeholder="Hamza Studio"
          value={values.business_name}
          onChangeText={(v) => set('business_name', v)}
        />
        <Input
          label="Tagline"
          placeholder="Weddings and portraits across Punjab"
          value={values.tagline}
          onChangeText={(v) => set('tagline', v)}
          maxLength={180}
        />
        <Input
          label="Bio"
          placeholder="Tell buyers what you shoot, how you work, and what makes your photos yours. At least 50 characters."
          value={values.bio}
          onChangeText={(v) => set('bio', v)}
          multiline
          numberOfLines={5}
          hint={`${values.bio.length} characters`}
        />

        <Text style={styles.section}>Professional</Text>
        <View style={styles.row}>
          <View style={styles.rowItem}>
            <Input
              label="Years experience"
              value={values.years_experience}
              onChangeText={(v) => set('years_experience', v.replace(/[^0-9]/g, ''))}
              keyboardType="number-pad"
            />
          </View>
          <View style={styles.rowItem}>
            <Input
              label="Travel radius (km)"
              value={values.service_radius_km}
              onChangeText={(v) => set('service_radius_km', v.replace(/[^0-9]/g, ''))}
              keyboardType="number-pad"
            />
          </View>
        </View>

        <Input
          label="Equipment"
          placeholder="Canon R5, 24-70 f/2.8, Godox lighting"
          value={values.equipment}
          onChangeText={(v) => set('equipment', v)}
          multiline
        />
        <Input
          label="Languages"
          placeholder="English, Urdu, Punjabi"
          value={values.languages}
          onChangeText={(v) => set('languages', v)}
        />

        <Text style={styles.section}>Links</Text>
        <Input
          label="Website"
          placeholder="https://…"
          value={values.website}
          onChangeText={(v) => set('website', v)}
          autoCapitalize="none"
          keyboardType="url"
          icon="globe-outline"
        />
        <Input
          label="Instagram"
          placeholder="yourhandle"
          value={values.instagram}
          onChangeText={(v) => set('instagram', v)}
          autoCapitalize="none"
          icon="logo-instagram"
        />

        <View style={styles.readOnly}>
          <Text style={styles.readOnlyTitle}>Managed elsewhere</Text>
          <Text style={styles.readOnlyText}>
            Your name, phone and city are account details — change them from
            Profile. Your "from" price comes from your cheapest live service.
            Verification and featuring are set by SnapSphere.
          </Text>
        </View>

        <Button
          label="Save profile"
          onPress={save}
          loading={updateProfile.isPending}
          disabled={form === null}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { ...typography.h3, color: colors.text },
  headerSpacer: { width: 24 },
  content: { padding: spacing.xl, paddingBottom: spacing.huge, gap: spacing.xs },
  notice: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  noticeText: { ...typography.caption, color: colors.amber, flex: 1, lineHeight: 18 },
  section: {
    ...typography.caption,
    color: colors.sub,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  row: { flexDirection: 'row', gap: spacing.sm },
  rowItem: { flex: 1 },
  readOnly: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginVertical: spacing.lg,
  },
  readOnlyTitle: { ...typography.caption, color: colors.text, fontWeight: '600' },
  readOnlyText: {
    ...typography.tiny,
    color: colors.sub,
    marginTop: spacing.xs,
    lineHeight: 16,
  },
});
