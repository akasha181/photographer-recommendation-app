import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import React from 'react';
import {
  Alert,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { Button } from '../../../components/ui/Button';
import { useAuthStore } from '../../../store/authStore';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatPKR } from '../../../utils/format';
import type {
  BuyerProfile,
  PhotographerSelfProfile,
} from '../../../types/models';
import { useChatUnreadTotal } from '../../chat/hooks/useChat';
import { useUnreadBadge } from '../../notifications/hooks/useNotifications';
import { usePendingReviews } from '../../reviews/hooks/useReviews';
import {
  useDeleteAccount,
  useMyProfile,
  useSellerSummary,
  useUpdateAccount,
  useUpdateProfile,
  useWallet,
  useWishlist,
} from '../../shop/hooks/useShop';

/**
 * The Profile tab, for both roles.
 *
 * ONE SCREEN, TWO SHAPES
 * ----------------------
 * The API returns a buyer profile or a photographer profile depending on who
 * asks, and the sections below switch on that. Two separate screens would
 * duplicate the header, the wallet card and every settings row — and those
 * are the parts most likely to drift apart.
 */
export function ProfileScreen({
  onOpenWallet,
  onOpenShop,
  onOpenWishlist,
  onOpenPurchases,
  onOpenBookings,
  onOpenSellerProducts,
  onOpenServices,
  onOpenCalendar,
  onEditProfile,
  onOpenReviews,
  onOpenMessages,
  onOpenNotifications,
  onOpenNotificationSettings,
}: {
  onOpenWallet?: () => void;
  onOpenShop?: () => void;
  onOpenWishlist: () => void;
  onOpenPurchases: () => void;
  onOpenBookings: () => void;
  onOpenSellerProducts?: () => void;
  /** Photographer-only — Module 5. Absent for buyers. */
  onOpenServices?: () => void;
  onOpenCalendar?: () => void;
  onEditProfile?: () => void;
  /** Module 9 — "my reviews" for a buyer, "reviews received" for a photographer. */
  onOpenReviews?: () => void;
  onOpenMessages?: () => void;
  onOpenNotifications?: () => void;
  onOpenNotificationSettings?: () => void;
}) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const profile = useMyProfile();
  const wallet = useWallet();
  const wishlist = useWishlist();
  const updateProfile = useUpdateProfile();
  const updateAccount = useUpdateAccount();
  const deleteAccount = useDeleteAccount();

  const [editingAccount, setEditingAccount] = React.useState(false);
  const [editName, setEditName] = React.useState(user?.full_name ?? '');
  const [editPhone, setEditPhone] = React.useState(user?.phone ?? '');
  const [editCity, setEditCity] = React.useState(user?.city ?? '');
  const [editAvatar, setEditAvatar] = React.useState<ImagePicker.ImagePickerAsset | null>(null);

  const isPhotographer = user?.role === 'PHOTOGRAPHER';
  const sellerSummary = useSellerSummary();

  const openEditAccount = () => {
    setEditName(user?.full_name ?? '');
    setEditPhone(user?.phone ?? '');
    setEditCity(user?.city ?? '');
    setEditAvatar(null);
    setEditingAccount(true);
  };

  const pickAvatar = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission needed', 'Please allow photo access to choose a profile picture.');
      return;
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.85,
    });
    if (!res.canceled && res.assets[0]) {
      setEditAvatar(res.assets[0]);
    }
  };

  const handleSaveAccount = () => {
    if (!editName.trim() || editName.trim().length < 3) {
      Alert.alert('Invalid Name', 'Please enter your full name (at least 3 characters).');
      return;
    }
    updateAccount.mutate(
      {
        full_name: editName.trim(),
        phone: editPhone.trim(),
        city: editCity.trim(),
        avatar: editAvatar
          ? {
              uri: editAvatar.uri,
              name: editAvatar.fileName ?? 'avatar.jpg',
              type: editAvatar.mimeType ?? 'image/jpeg',
            }
          : undefined,
      },
      {
        onSuccess: () => {
          setEditingAccount(false);
          Alert.alert('Saved', 'Your account details have been updated.');
        },
        onError: (err) => {
          Alert.alert('Update Failed', (err as ApiError)?.message ?? 'Could not update profile.');
        },
      },
    );
  };

  const confirmDeleteAccount = () =>
    Alert.alert(
      'Delete Account?',
      'Are you sure you want to permanently delete your account? This action cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete Account',
          style: 'destructive',
          onPress: () => {
            deleteAccount.mutate(undefined, {
              onSuccess: () => {
                Alert.alert('Account Deleted', 'Account successfully deleted.');
              },
              onError: (error) => {
                Alert.alert(
                  'Could not delete account',
                  (error as ApiError)?.message ?? 'Please try again later.',
                );
              },
            });
          },
        },
      ],
    );

  // Counters for the rows below. Each is its own cached query, so the same
  // number shown here and on the bell can never disagree.
  const badge = useUnreadBadge();
  const chatUnread = useChatUnreadTotal();
  const pendingReviews = usePendingReviews();

  if (profile.isLoading) return <LoadingState label="Loading your profile…" />;
  if (profile.isError || !profile.data) {
    return (
      <ErrorState
        message={(profile.error as ApiError)?.message}
        onRetry={() => profile.refetch()}
      />
    );
  }

  const photographerProfile = isPhotographer
    ? (profile.data as PhotographerSelfProfile)
    : null;
  const buyerProfile = isPhotographer ? null : (profile.data as BuyerProfile);

  const confirmLogout = () =>
    Alert.alert('Log out?', 'You will need to sign in again.', [
      { text: 'Stay', style: 'cancel' },
      { text: 'Log out', style: 'destructive', onPress: () => logout() },
    ]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={profile.isRefetching}
            onRefresh={() => {
              profile.refetch();
              wallet.refetch();
            }}
            tintColor={colors.gold}
          />
        }
      >
        {/* ─── Identity ────────────────────────────────────────────────── */}
        <View style={styles.header}>
          <Avatar
            uri={user?.avatar_url}
            name={user?.full_name ?? '?'}
            size={64}
          />
          <View style={styles.headerBody}>
            <Text style={styles.name}>{user?.full_name}</Text>
            <Text style={styles.email}>{user?.email}</Text>
            <View style={styles.badges}>
              <View style={styles.rolePill}>
                <Text style={styles.rolePillText}>
                  {isPhotographer ? 'Photographer' : 'Buyer'}
                </Text>
              </View>
              {user?.is_email_verified ? (
                <View style={styles.verifiedPill}>
                  <Ionicons name="checkmark-circle" size={11} color={colors.green} />
                  <Text style={styles.verifiedText}>Verified</Text>
                </View>
              ) : null}
            </View>
          </View>
        </View>

        {photographerProfile && !photographerProfile.is_approved ? (
          <View style={styles.pending}>
            <Ionicons name="hourglass-outline" size={16} color={colors.amber} />
            <Text style={styles.pendingText}>
              {photographerProfile.rejection_reason ||
                'Your profile is awaiting admin approval. Buyers cannot find you yet.'}
            </Text>
          </View>
        ) : null}

        {/* ─── Stats ───────────────────────────────────────────────────── */}
        {buyerProfile ? (
          <View style={styles.stats}>
            <Stat value={String(buyerProfile.total_bookings)} label="Bookings" />
            <Stat value={String(buyerProfile.completed_bookings)} label="Completed" />
            <Stat value={formatPKR(buyerProfile.total_spent)} label="Spent" />
          </View>
        ) : photographerProfile ? (
          <View style={styles.stats}>
            <Stat value={String(photographerProfile.completed_bookings)} label="Shoots" />
            <Stat value={photographerProfile.avg_rating} label="Rating" />
            <Stat
              value={formatPKR(photographerProfile.total_earnings)}
              label="Earned"
            />
          </View>
        ) : null}

        {/* ─── Photographer availability toggle ────────────────────────── */}
        {photographerProfile ? (
          <View style={styles.toggleRow}>
            <View style={styles.toggleBody}>
              <Text style={styles.toggleTitle}>Accepting bookings</Text>
              <Text style={styles.toggleDetail}>
                Turn this off while you are away. Existing bookings are not
                affected.
              </Text>
            </View>
            <Switch
              value={photographerProfile.is_accepting_bookings}
              onValueChange={(value) =>
                updateProfile.mutate(
                  { is_accepting_bookings: value },
                  {
                    onError: (error) =>
                      Alert.alert('Could not change that', (error as ApiError).message),
                  },
                )
              }
              trackColor={{ false: colors.border, true: colors.goldDim }}
              thumbColor={
                photographerProfile.is_accepting_bookings ? colors.gold : colors.sub
              }
            />
          </View>
        ) : null}

        {/* ─── Studio (photographer only) ──────────────────────────────── */}
        {photographerProfile ? (
          <Section title="Your studio">
            {onOpenServices ? (
              <Row
                icon="camera-outline"
                label="Services & pricing"
                value={String(photographerProfile.services?.length ?? 0)}
                onPress={onOpenServices}
              />
            ) : null}
            {onOpenCalendar ? (
              <Row
                icon="calendar-outline"
                label="Availability"
                onPress={onOpenCalendar}
              />
            ) : null}
            {onEditProfile ? (
              <Row
                icon="create-outline"
                label="Edit public profile"
                onPress={onEditProfile}
              />
            ) : null}
            {onOpenSellerProducts ? (
              <Row
                icon="pricetags-outline"
                label="My products"
                value={
                  sellerSummary.data ? String(sellerSummary.data.products_live) : undefined
                }
                onPress={onOpenSellerProducts}
              />
            ) : null}
          </Section>
        ) : null}

        {/* ─── Navigation ──────────────────────────────────────────────── */}
        <Section title="Your activity">
          <Row
            icon="calendar-outline"
            label={isPhotographer ? 'Bookings' : 'My bookings'}
            onPress={onOpenBookings}
          />
          <Row
            icon="heart-outline"
            label="Saved"
            value={
              wishlist.data
                ? String(
                    wishlist.data.counts.photographers + wishlist.data.counts.products,
                  )
                : undefined
            }
            onPress={onOpenWishlist}
          />
          <Row icon="download-outline" label="Purchases" onPress={onOpenPurchases} />
          {onOpenShop ? (
            <Row icon="bag-handle-outline" label="Shop" onPress={onOpenShop} />
          ) : null}
          {onOpenReviews ? (
            <Row
              icon="star-outline"
              label={isPhotographer ? 'Reviews received' : 'My reviews'}
              // The badge is the outstanding count on each side: replies owed
              // for a photographer, reviews owed for a buyer.
              value={
                isPhotographer
                  ? undefined
                  : pendingReviews.data
                    ? String(
                        pendingReviews.data.bookings.length +
                          pendingReviews.data.order_items.length,
                      )
                    : undefined
              }
              onPress={onOpenReviews}
            />
          ) : null}
          {onOpenMessages ? (
            <Row
              icon="chatbubbles-outline"
              label="Messages"
              value={
                chatUnread.data?.unread_total
                  ? String(chatUnread.data.unread_total)
                  : undefined
              }
              onPress={onOpenMessages}
            />
          ) : null}
        </Section>

        <Section title="Account">
          <Row
            icon="create-outline"
            label="Edit account details"
            value="Edit"
            onPress={openEditAccount}
          />
          <Row icon="person-outline" label={user?.full_name ?? 'Profile'} muted />
          <Row icon="call-outline" label={user?.phone || 'No phone added'} muted />
          <Row icon="location-outline" label={user?.city || 'No city set'} muted />
          {onOpenNotifications ? (
            <Row
              icon="notifications-outline"
              label="Notifications"
              value={badge.data?.total ? String(badge.data.total) : undefined}
              onPress={onOpenNotifications}
            />
          ) : null}
          {onOpenNotificationSettings ? (
            <Row
              icon="options-outline"
              label="Notification settings"
              onPress={onOpenNotificationSettings}
            />
          ) : null}
        </Section>

        <Pressable onPress={confirmLogout} style={styles.logout}>
          <Ionicons name="log-out-outline" size={18} color={colors.red} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>

        <Pressable onPress={confirmDeleteAccount} style={styles.deleteBtn}>
          <Ionicons name="trash-outline" size={18} color={colors.red} />
          <Text style={styles.deleteBtnText}>Delete account</Text>
        </Pressable>

        <Text style={styles.version}>SnapSphere · v1.0.0</Text>
      </ScrollView>

      {/* ─── Edit Account Modal ────────────────────────────────────── */}
      <Modal
        visible={editingAccount}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setEditingAccount(false)}
      >
        <SafeAreaView style={styles.modalSafe} edges={['top', 'bottom']}>
          <View style={styles.modalHeader}>
            <Pressable onPress={() => setEditingAccount(false)} hitSlop={10}>
              <Ionicons name="close" size={24} color={colors.text} />
            </Pressable>
            <Text style={styles.modalTitle}>Edit Account</Text>
            <View style={{ width: 24 }} />
          </View>

          <ScrollView contentContainerStyle={styles.modalContent} showsVerticalScrollIndicator={false}>
            <View style={styles.avatarPickerContainer}>
              <Avatar
                uri={editAvatar ? editAvatar.uri : user?.avatar_url}
                name={editName || '?'}
                size={84}
              />
              <Pressable onPress={pickAvatar} style={styles.changeAvatarBtn}>
                <Ionicons name="camera" size={16} color={colors.gold} />
                <Text style={styles.changeAvatarText}>Change Photo</Text>
              </Pressable>
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.inputLabel}>Full Name</Text>
              <TextInput
                value={editName}
                onChangeText={setEditName}
                placeholder="Your full name"
                placeholderTextColor={colors.dim}
                style={styles.modalInput}
              />
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.inputLabel}>Phone Number</Text>
              <TextInput
                value={editPhone}
                onChangeText={setEditPhone}
                placeholder="+92 300 1234567"
                placeholderTextColor={colors.dim}
                keyboardType="phone-pad"
                style={styles.modalInput}
              />
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.inputLabel}>City</Text>
              <TextInput
                value={editCity}
                onChangeText={setEditCity}
                placeholder="e.g. Lahore, Karachi, Islamabad"
                placeholderTextColor={colors.dim}
                style={styles.modalInput}
              />
            </View>

            <View style={styles.modalActions}>
              <Button
                label={updateAccount.isPending ? 'Saving...' : 'Save Changes'}
                onPress={handleSaveAccount}
                disabled={updateAccount.isPending}
                size="lg"
              />
            </View>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue} numberOfLines={1}>
        {value}
      </Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function Row({
  icon,
  label,
  value,
  onPress,
  muted,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value?: string;
  onPress?: () => void;
  muted?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      style={({ pressed }) => [styles.row, pressed && onPress && styles.rowPressed]}
    >
      <Ionicons name={icon} size={18} color={muted ? colors.dim : colors.gold} />
      <Text style={[styles.rowLabel, muted && styles.rowLabelMuted]} numberOfLines={1}>
        {label}
      </Text>
      {value ? <Text style={styles.rowValue}>{value}</Text> : null}
      {onPress ? (
        <Ionicons name="chevron-forward" size={16} color={colors.dim} />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.xl, paddingBottom: spacing.huge },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  headerBody: { flex: 1 },
  name: { ...typography.h2, color: colors.text },
  email: { ...typography.caption, color: colors.sub },
  badges: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  rolePill: {
    backgroundColor: colors.goldDim,
    paddingHorizontal: spacing.md,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  rolePillText: { ...typography.tiny, color: colors.goldLight, fontWeight: '700' },
  verifiedPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.greenDim,
    paddingHorizontal: spacing.md,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  verifiedText: { ...typography.tiny, color: colors.green, fontWeight: '600' },
  pending: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  pendingText: { ...typography.caption, color: colors.amber, flex: 1, lineHeight: 18 },
  walletCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderMid,
    padding: spacing.lg,
    marginTop: spacing.xl,
  },
  walletTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  walletLabel: { ...typography.caption, color: colors.sub },
  walletAmount: { ...typography.display, color: colors.gold, marginTop: spacing.xs },
  walletHint: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  walletPending: { ...typography.tiny, color: colors.amber, marginTop: spacing.xs },
  stats: {
    flexDirection: 'row',
    marginTop: spacing.lg,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.lg,
  },
  stat: { flex: 1, alignItems: 'center', paddingHorizontal: spacing.sm },
  statValue: { ...typography.bodyBold, color: colors.text },
  statLabel: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginTop: spacing.lg,
  },
  toggleBody: { flex: 1 },
  toggleTitle: { ...typography.bodyBold, color: colors.text },
  toggleDetail: { ...typography.tiny, color: colors.sub, marginTop: 2, lineHeight: 15 },
  section: { marginTop: spacing.xxl },
  sectionTitle: {
    ...typography.caption,
    color: colors.sub,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  sectionBody: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowPressed: { backgroundColor: colors.cardHover },
  rowLabel: { ...typography.body, color: colors.text, flex: 1 },
  rowLabelMuted: { color: colors.sub },
  rowValue: { ...typography.caption, color: colors.gold, fontWeight: '600' },
  logout: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.xxl,
    paddingVertical: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.redDim,
    backgroundColor: colors.redDim,
  },
  logoutText: { ...typography.bodyBold, color: colors.red },
  deleteBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
  },
  deleteBtnText: { ...typography.caption, fontWeight: '700' as const, color: colors.red },
  modalSafe: { flex: 1, backgroundColor: colors.bg },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  modalTitle: { ...typography.h3, color: colors.text },
  modalContent: { padding: spacing.xl, gap: spacing.lg },
  avatarPickerContainer: {
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  changeAvatarBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.goldDim,
  },
  changeAvatarText: { ...typography.caption, fontWeight: '700' as const, color: colors.gold },
  formGroup: { gap: spacing.xs },
  inputLabel: { ...typography.caption, fontWeight: '700' as const, color: colors.sub },
  modalInput: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    color: colors.text,
    ...typography.body,
  },
  modalActions: { marginTop: spacing.lg },
  version: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginTop: spacing.xl,
  },
});
