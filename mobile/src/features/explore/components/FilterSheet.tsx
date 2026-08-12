import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { PhotographerFilters } from '../../../api/services/photographers.api';
import { Button } from '../../../components/ui/Button';
import { formatPKR } from '../../../utils/format';
import { colors, radius, spacing, typography } from '../../../theme';
import { useFilterOptions } from '../hooks/usePhotographers';

interface Props {
  visible: boolean;
  filters: PhotographerFilters;
  onClose: () => void;
  onApply: (filters: PhotographerFilters) => void;
}

/**
 * Filter sheet.
 *
 * Cities and the price range come from GET /photographers/filters/, not from
 * a hard-coded list. A static "Rs 0–200,000" slider is wrong the moment a
 * photographer prices outside it, and a static city list silently hides every
 * city that gains its first photographer later.
 *
 * Edits are held in local state and only lifted on Apply, so backing out of
 * the sheet leaves the results untouched.
 */
export function FilterSheet({ visible, filters, onClose, onApply }: Props) {
  const options = useFilterOptions();
  const [draft, setDraft] = useState<PhotographerFilters>(filters);

  // Resync whenever the sheet reopens — otherwise it shows the previous
  // session's edits after a cancel.
  useEffect(() => {
    if (visible) setDraft(filters);
  }, [visible, filters]);

  const priceMin = options.data?.price_range.min ?? 0;
  const priceMax = options.data?.price_range.max ?? 200000;

  const budgetSteps = buildBudgetSteps(priceMin, priceMax);

  const update = (patch: Partial<PhotographerFilters>) =>
    setDraft((prev) => ({ ...prev, ...patch }));

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose} />

      <View style={styles.sheet}>
        <View style={styles.handle} />

        <View style={styles.header}>
          <Text style={styles.title}>Filters</Text>
          <Pressable onPress={() => setDraft({})} hitSlop={8}>
            <Text style={styles.reset}>Reset all</Text>
          </Pressable>
        </View>

        <ScrollView showsVerticalScrollIndicator={false}>
          {/* ─── City ─────────────────────────────────────────────────── */}
          <Section title="City">
            <View style={styles.wrap}>
              <Chip
                label="Any"
                active={!draft.city}
                onPress={() => update({ city: undefined })}
              />
              {(options.data?.cities ?? []).slice(0, 10).map((city) => (
                <Chip
                  key={city.name}
                  label={`${city.name} (${city.count})`}
                  active={draft.city === city.name}
                  onPress={() =>
                    update({ city: draft.city === city.name ? undefined : city.name })
                  }
                />
              ))}
            </View>
          </Section>

          {/* ─── Budget ───────────────────────────────────────────────── */}
          <Section title="Maximum budget">
            <View style={styles.wrap}>
              <Chip
                label="Any"
                active={!draft.max_price}
                onPress={() => update({ max_price: undefined })}
              />
              {budgetSteps.map((amount) => (
                <Chip
                  key={amount}
                  label={`under ${formatPKR(amount)}`}
                  active={draft.max_price === amount}
                  onPress={() =>
                    update({
                      max_price: draft.max_price === amount ? undefined : amount,
                    })
                  }
                />
              ))}
            </View>
            <Text style={styles.hint}>
              Prices on SnapSphere range from {formatPKR(priceMin)} to{' '}
              {formatPKR(priceMax)}
            </Text>
          </Section>

          {/* ─── Rating ───────────────────────────────────────────────── */}
          <Section title="Minimum rating">
            <View style={styles.wrap}>
              <Chip
                label="Any"
                active={!draft.min_rating}
                onPress={() => update({ min_rating: undefined })}
              />
              {[3, 3.5, 4, 4.5].map((rating) => (
                <Chip
                  key={rating}
                  label={`${rating}★ +`}
                  active={draft.min_rating === rating}
                  onPress={() =>
                    update({
                      min_rating: draft.min_rating === rating ? undefined : rating,
                    })
                  }
                />
              ))}
            </View>
          </Section>

          {/* ─── Experience ───────────────────────────────────────────── */}
          <Section title="Minimum experience">
            <View style={styles.wrap}>
              <Chip
                label="Any"
                active={!draft.min_experience}
                onPress={() => update({ min_experience: undefined })}
              />
              {[2, 5, 10].map((years) => (
                <Chip
                  key={years}
                  label={`${years}+ years`}
                  active={draft.min_experience === years}
                  onPress={() =>
                    update({
                      min_experience:
                        draft.min_experience === years ? undefined : years,
                    })
                  }
                />
              ))}
            </View>
          </Section>

          {/* ─── Badges ───────────────────────────────────────────────── */}
          <Section title="Only show">
            <View style={styles.wrap}>
              <Chip
                label="Verified"
                active={draft.verified === true}
                onPress={() =>
                  update({ verified: draft.verified ? undefined : true })
                }
              />
              <Chip
                label="Accepting bookings"
                active={draft.available === true}
                onPress={() =>
                  update({ available: draft.available ? undefined : true })
                }
              />
            </View>
          </Section>

          {/* ─── Sort ─────────────────────────────────────────────────── */}
          <Section title="Sort by">
            <View style={styles.wrap}>
              {(options.data?.sort_options ?? []).map((option) => (
                <Chip
                  key={option.value}
                  label={option.label}
                  active={draft.ordering === option.value}
                  onPress={() =>
                    update({
                      ordering:
                        draft.ordering === option.value ? undefined : option.value,
                    })
                  }
                />
              ))}
            </View>
          </Section>
        </ScrollView>

        <View style={styles.actions}>
          <Button label="Show results" onPress={() => onApply(draft)} size="lg" />
        </View>
      </View>
    </Modal>
  );
}

/** Round budget steps derived from the real price range in the data. */
function buildBudgetSteps(min: number, max: number): number[] {
  const span = max - min;
  if (span <= 0) return [];
  return [0.25, 0.5, 0.75, 1]
    .map((fraction) => Math.round((min + span * fraction) / 5000) * 5000)
    .filter((value, index, all) => value > 0 && all.indexOf(value) === index);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Chip({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={[styles.chip, active && styles.chipActive]}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xxxl,
    maxHeight: '84%',
  },
  handle: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderMid,
    alignSelf: 'center',
    marginTop: spacing.md,
    marginBottom: spacing.lg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  title: { ...typography.h2, color: colors.text },
  reset: { ...typography.caption, color: colors.gold, fontWeight: '600' },
  section: { marginBottom: spacing.xxl },
  sectionTitle: {
    ...typography.caption,
    color: colors.sub,
    fontWeight: '700',
    marginBottom: spacing.md,
  },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  chipTextActive: { color: colors.bg },
  hint: { ...typography.tiny, color: colors.dim, marginTop: spacing.md },
  actions: {
    paddingTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
});
