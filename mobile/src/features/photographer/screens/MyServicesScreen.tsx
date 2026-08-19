import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { useCategories } from '../../explore/hooks/usePhotographers';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatPKR } from '../../../utils/format';
import type { OwnService } from '../../../types/models';
import {
  useArchiveService,
  useCreateService,
  useDeleteService,
  useMyServices,
  useRestoreService,
  useUpdateService,
} from '../hooks/useMyStudio';

const PRICING_UNITS = [
  { value: 'FIXED', label: 'Fixed price' },
  { value: 'PER_HOUR', label: 'Per hour' },
  { value: 'PER_DAY', label: 'Per day' },
] as const;

/**
 * What this photographer sells.
 *
 * ARCHIVE VS DELETE IS SURFACED, NOT HIDDEN
 * -----------------------------------------
 * `Booking.service` is PROTECT and every booking snapshots its price, so a
 * service with history cannot be removed without breaking that history. The
 * server sends `can_delete`, and the row offers Archive or Delete
 * accordingly — instead of showing Delete and failing on tap.
 */
export function MyServicesScreen({ onBack }: { onBack: () => void }) {
  const services = useMyServices();
  const categories = useCategories();

  const createService = useCreateService();
  const updateService = useUpdateService();
  const archiveService = useArchiveService();
  const restoreService = useRestoreService();
  const deleteService = useDeleteService();

  const [editing, setEditing] = useState<OwnService | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [form, setForm] = useState(blankForm());

  const openNew = () => {
    setEditing(null);
    setForm(blankForm());
    setSheetOpen(true);
  };

  const openEdit = (service: OwnService) => {
    setEditing(service);
    setForm({
      title: service.title,
      description: service.description,
      price: String(Math.round(Number(service.price))),
      category: service.category?.id ?? null,
      pricing_unit: service.pricing_unit,
      duration_hours: String(service.duration_hours),
      edited_photos_count: String(service.edited_photos_count),
      delivery_days: String(service.delivery_days),
      includes: (service.includes ?? []).join('\n'),
    });
    setSheetOpen(true);
  };

  const fail = (error: unknown) =>
    Alert.alert('Could not save', (error as ApiError)?.message ?? 'Please try again.');

  const submit = () => {
    if (!form.category) {
      Alert.alert('Category needed', 'Pick the event type this service is for.');
      return;
    }
    const payload = {
      title: form.title.trim(),
      description: form.description.trim(),
      category: form.category,
      price: form.price || '0',
      pricing_unit: form.pricing_unit,
      duration_hours: Number(form.duration_hours) || 1,
      edited_photos_count: Number(form.edited_photos_count) || 0,
      delivery_days: Number(form.delivery_days) || 7,
      includes: form.includes
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    };

    const done = { onSuccess: () => setSheetOpen(false), onError: fail };
    if (editing) {
      updateService.mutate({ id: editing.id, payload }, done);
    } else {
      createService.mutate(payload, done);
    }
  };

  const confirmRemove = (service: OwnService) => {
    if (service.can_delete) {
      Alert.alert('Delete this service?', 'This cannot be undone.', [
        { text: 'Keep', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => deleteService.mutate(service.id, { onError: fail }),
        },
      ]);
      return;
    }
    Alert.alert(
      'Archive this service?',
      `It has ${service.booking_count} booking(s), so it cannot be deleted — your history stays intact. Archiving hides it from buyers.`,
      [
        { text: 'Keep live', style: 'cancel' },
        {
          text: 'Archive',
          onPress: () => archiveService.mutate(service.id, { onError: fail }),
        },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>My services</Text>
        <Pressable onPress={openNew} hitSlop={12} accessibilityLabel="Add a service">
          <Ionicons name="add" size={26} color={colors.gold} />
        </Pressable>
      </View>

      {services.isLoading ? (
        <LoadingState label="Loading your services…" />
      ) : services.isError ? (
        <ErrorState
          message={(services.error as ApiError)?.message}
          onRetry={() => services.refetch()}
        />
      ) : (
        <FlatList
          data={services.data ?? []}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={services.data?.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <ServiceRow
              service={item}
              onEdit={() => openEdit(item)}
              onRemove={() => confirmRemove(item)}
              onRestore={() => restoreService.mutate(item.id, { onError: fail })}
            />
          )}
          ListHeaderComponent={
            services.data?.length ? (
              <Text style={styles.hint}>
                These are what buyers book. Your profile shows the cheapest as
                "from".
              </Text>
            ) : null
          }
          ListEmptyComponent={
            <EmptyState
              icon="camera-outline"
              title="No services yet"
              detail="Add what you offer — a wedding package, an hourly portrait session — so buyers have something to book."
              actionLabel="Add your first service"
              onAction={openNew}
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={services.isRefetching}
              onRefresh={() => services.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      )}

      {/* ─── Editor sheet ────────────────────────────────────────────────── */}
      <Modal
        visible={sheetOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setSheetOpen(false)}
      >
        <View style={styles.backdrop}>
          <ScrollView
            style={styles.sheet}
            contentContainerStyle={styles.sheetContent}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={styles.sheetTitle}>
              {editing ? 'Edit service' : 'New service'}
            </Text>
            {editing ? (
              <Text style={styles.sheetDetail}>
                Changing the price here does not affect bookings you already
                have — those keep the price the buyer agreed to.
              </Text>
            ) : null}

            <Input
              label="Title"
              placeholder="Full-Day Wedding Coverage"
              value={form.title}
              onChangeText={(title) => setForm({ ...form, title })}
            />

            <Text style={styles.fieldLabel}>Event type</Text>
            <View style={styles.chips}>
              {(categories.data ?? []).map((entry) => (
                <Pressable
                  key={entry.id}
                  onPress={() => setForm({ ...form, category: entry.id })}
                  style={[styles.chip, form.category === entry.id && styles.chipActive]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      form.category === entry.id && styles.chipTextActive,
                    ]}
                  >
                    {entry.name}
                  </Text>
                </Pressable>
              ))}
            </View>

            <Input
              label="Price (PKR)"
              placeholder="85000"
              value={form.price}
              onChangeText={(price) =>
                setForm({ ...form, price: price.replace(/[^0-9]/g, '') })
              }
              keyboardType="number-pad"
              icon="cash-outline"
            />

            <Text style={styles.fieldLabel}>Charged as</Text>
            <View style={styles.chips}>
              {PRICING_UNITS.map((unit) => (
                <Pressable
                  key={unit.value}
                  onPress={() => setForm({ ...form, pricing_unit: unit.value })}
                  style={[
                    styles.chip,
                    form.pricing_unit === unit.value && styles.chipActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      form.pricing_unit === unit.value && styles.chipTextActive,
                    ]}
                  >
                    {unit.label}
                  </Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.row}>
              <View style={styles.rowItem}>
                <Input
                  label="Hours"
                  value={form.duration_hours}
                  onChangeText={(v) =>
                    setForm({ ...form, duration_hours: v.replace(/[^0-9]/g, '') })
                  }
                  keyboardType="number-pad"
                />
              </View>
              <View style={styles.rowItem}>
                <Input
                  label="Edited photos"
                  value={form.edited_photos_count}
                  onChangeText={(v) =>
                    setForm({ ...form, edited_photos_count: v.replace(/[^0-9]/g, '') })
                  }
                  keyboardType="number-pad"
                />
              </View>
              <View style={styles.rowItem}>
                <Input
                  label="Delivery days"
                  value={form.delivery_days}
                  onChangeText={(v) =>
                    setForm({ ...form, delivery_days: v.replace(/[^0-9]/g, '') })
                  }
                  keyboardType="number-pad"
                />
              </View>
            </View>

            <Input
              label="Description"
              placeholder="What the buyer gets, in a sentence or two."
              value={form.description}
              onChangeText={(description) => setForm({ ...form, description })}
              multiline
              numberOfLines={3}
            />

            <Input
              label="What's included (one per line)"
              placeholder={'2 photographers\nDrone shots\nOnline gallery'}
              value={form.includes}
              onChangeText={(includes) => setForm({ ...form, includes })}
              multiline
              numberOfLines={4}
            />

            <Button
              label={editing ? 'Save changes' : 'Publish service'}
              onPress={submit}
              loading={createService.isPending || updateService.isPending}
            />
            <Button label="Cancel" variant="ghost" onPress={() => setSheetOpen(false)} />
          </ScrollView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function blankForm() {
  return {
    title: '',
    description: '',
    price: '',
    category: null as number | null,
    pricing_unit: 'FIXED' as OwnService['pricing_unit'],
    duration_hours: '4',
    edited_photos_count: '50',
    delivery_days: '14',
    includes: '',
  };
}

function ServiceRow({
  service,
  onEdit,
  onRemove,
  onRestore,
}: {
  service: OwnService;
  onEdit: () => void;
  onRemove: () => void;
  onRestore: () => void;
}) {
  return (
    <View style={[styles.card, !service.is_active && styles.cardArchived]}>
      <Pressable onPress={onEdit} style={styles.cardMain} accessibilityRole="button">
        <View style={styles.cardBody}>
          <View style={styles.titleRow}>
            <Text style={styles.title} numberOfLines={2}>
              {service.title}
            </Text>
            {!service.is_active ? (
              <View style={styles.archivedPill}>
                <Text style={styles.archivedText}>ARCHIVED</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.meta}>
            {service.category?.name} · {service.duration_hours}h ·{' '}
            {service.edited_photos_count} photos
          </Text>
          <Text style={styles.bookings}>
            {service.booking_count === 0
              ? 'No bookings yet'
              : `${service.booking_count} booking${service.booking_count === 1 ? '' : 's'}`}
          </Text>
        </View>
        <View style={styles.priceCol}>
          <Text style={styles.price}>{formatPKR(service.price)}</Text>
          <Text style={styles.unit}>
            {service.pricing_unit === 'PER_HOUR' ? 'per hour' : 'total'}
          </Text>
        </View>
      </Pressable>

      <View style={styles.actions}>
        {service.is_active ? (
          <>
            <Pressable onPress={onEdit} style={styles.action} hitSlop={8}>
              <Ionicons name="create-outline" size={16} color={colors.sub} />
              <Text style={styles.actionText}>Edit</Text>
            </Pressable>
            <Pressable onPress={onRemove} style={styles.action} hitSlop={8}>
              <Ionicons
                name={service.can_delete ? 'trash-outline' : 'archive-outline'}
                size={16}
                color={colors.red}
              />
              <Text style={[styles.actionText, styles.danger]}>
                {service.can_delete ? 'Delete' : 'Archive'}
              </Text>
            </Pressable>
          </>
        ) : (
          <Pressable onPress={onRestore} style={styles.action} hitSlop={8}>
            <Ionicons name="refresh-outline" size={16} color={colors.green} />
            <Text style={[styles.actionText, styles.restore]}>Put back on sale</Text>
          </Pressable>
        )}
      </View>
    </View>
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
  list: { padding: spacing.xl },
  listEmpty: { flexGrow: 1 },
  hint: { ...typography.caption, color: colors.sub, marginBottom: spacing.lg },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardArchived: { opacity: 0.6 },
  cardMain: { flexDirection: 'row', gap: spacing.md },
  cardBody: { flex: 1 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  title: { ...typography.bodyBold, color: colors.text, flexShrink: 1 },
  archivedPill: {
    backgroundColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: 1,
    borderRadius: radius.sm,
  },
  archivedText: { ...typography.tiny, color: colors.sub, fontWeight: '700' },
  meta: { ...typography.caption, color: colors.sub, marginTop: 2 },
  bookings: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  priceCol: { alignItems: 'flex-end' },
  price: { ...typography.bodyBold, color: colors.gold },
  unit: { ...typography.tiny, color: colors.dim },
  actions: {
    flexDirection: 'row',
    gap: spacing.xl,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  action: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs + 2 },
  actionText: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  danger: { color: colors.red },
  restore: { color: colors.green },
  backdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '92%',
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  sheetContent: { padding: spacing.xl, paddingBottom: spacing.xxxl, gap: spacing.sm },
  sheetTitle: { ...typography.h2, color: colors.text },
  sheetDetail: {
    ...typography.caption,
    color: colors.sub,
    lineHeight: 19,
    marginBottom: spacing.md,
  },
  fieldLabel: { ...typography.caption, color: colors.sub, marginBottom: spacing.xs },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  chipActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  chipTextActive: { color: colors.bg },
  row: { flexDirection: 'row', gap: spacing.sm },
  rowItem: { flex: 1 },
});
