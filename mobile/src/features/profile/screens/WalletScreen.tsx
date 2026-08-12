import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import React, { useState } from 'react';
import {
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate, formatPKR, timeAgo } from '../../../utils/format';
import type { TopUpRequest, WalletTransaction } from '../../../types/models';
import {
  useRequestTopUp,
  useTopUps,
  useTransactions,
  useWallet,
} from '../../shop/hooks/useShop';

const METHODS = [
  { value: 'BANK', label: 'Bank transfer' },
  { value: 'EASYPAISA', label: 'Easypaisa' },
  { value: 'JAZZCASH', label: 'JazzCash' },
];

/**
 * Wallet, ledger and top-ups.
 *
 * WHY TOPPING UP IS NOT INSTANT
 * -----------------------------
 * The proposal excludes an online payment gateway, so money enters the
 * platform one way: the user transfers it themselves, uploads the receipt,
 * and an admin verifies it before the balance moves. The screen says so
 * plainly — a user who expects instant credit and does not get it assumes the
 * app is broken.
 */
export function WalletScreen({ onBack }: { onBack: () => void }) {
  const wallet = useWallet();
  const transactions = useTransactions();
  const topups = useTopUps();
  const requestTopUp = useRequestTopUp();

  const [sheetOpen, setSheetOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('BANK');
  const [reference, setReference] = useState('');
  const [receipt, setReceipt] = useState<ImagePicker.ImagePickerAsset | null>(null);

  const pickReceipt = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        'Photo access needed',
        'We need access to your photos so you can attach the transfer receipt.',
      );
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.7,
    });
    if (!result.canceled) setReceipt(result.assets[0]);
  };

  const submit = () => {
    if (!amount || Number(amount) < 100) {
      Alert.alert('Amount too small', 'The minimum top-up is Rs 100.');
      return;
    }
    if (reference.trim().length < 4) {
      Alert.alert(
        'Reference needed',
        'Enter the reference number printed on your transfer receipt.',
      );
      return;
    }
    if (!receipt) {
      Alert.alert('Receipt needed', 'Attach a photo of your transfer receipt.');
      return;
    }

    requestTopUp.mutate(
      {
        amount,
        method,
        transaction_reference: reference.trim(),
        receipt: {
          uri: receipt.uri,
          name: receipt.fileName ?? 'receipt.jpg',
          type: receipt.mimeType ?? 'image/jpeg',
        },
      },
      {
        onSuccess: () => {
          setSheetOpen(false);
          setAmount('');
          setReference('');
          setReceipt(null);
          Alert.alert(
            'Receipt submitted',
            'An admin will verify it and your balance will be credited. This usually takes a few hours.',
          );
        },
        onError: (error) =>
          Alert.alert('Could not submit', (error as ApiError).message),
      },
    );
  };

  if (wallet.isLoading) return <LoadingState label="Loading your wallet…" />;
  if (wallet.isError || !wallet.data) {
    return (
      <ErrorState
        message={(wallet.error as ApiError)?.message}
        onRetry={() => wallet.refetch()}
      />
    );
  }

  const pending = (topups.data ?? []).filter((t) => t.status === 'PENDING');

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>Wallet</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Available balance</Text>
          <Text style={styles.balance}>{formatPKR(wallet.data.balance)}</Text>
          <View style={styles.balanceMeta}>
            <Text style={styles.balanceMetaText}>
              In {formatPKR(wallet.data.total_credited)}
            </Text>
            <Text style={styles.balanceMetaText}>
              Out {formatPKR(wallet.data.total_debited)}
            </Text>
          </View>
        </View>

        <Button label="Add funds" onPress={() => setSheetOpen(true)} />

        {pending.length ? (
          <View style={styles.pending}>
            <Ionicons name="hourglass-outline" size={16} color={colors.amber} />
            <Text style={styles.pendingText}>
              {pending.length === 1
                ? `${formatPKR(pending[0].amount)} awaiting admin verification.`
                : `${pending.length} top-ups awaiting admin verification.`}
            </Text>
          </View>
        ) : null}

        {/* ─── Ledger ──────────────────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Transactions</Text>
        {transactions.isLoading ? (
          <Text style={styles.hint}>Loading…</Text>
        ) : (transactions.data ?? []).length === 0 ? (
          <Text style={styles.hint}>No transactions yet.</Text>
        ) : (
          <View style={styles.ledger}>
            {(transactions.data ?? []).map((row) => (
              <LedgerRow key={row.id} row={row} />
            ))}
          </View>
        )}

        {/* ─── Top-up history ──────────────────────────────────────────── */}
        {(topups.data ?? []).length ? (
          <>
            <Text style={styles.sectionTitle}>Top-up requests</Text>
            <View style={styles.ledger}>
              {(topups.data ?? []).map((row) => (
                <TopUpRow key={row.id} row={row} />
              ))}
            </View>
          </>
        ) : null}
      </ScrollView>

      {/* ─── Top-up sheet ────────────────────────────────────────────────── */}
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
            <Text style={styles.sheetTitle}>Add funds</Text>
            <Text style={styles.sheetDetail}>
              Transfer the amount to the SnapSphere account, then upload the
              receipt. An admin verifies it before your balance is credited —
              nothing is charged through the app.
            </Text>

            <Input
              label="Amount (PKR)"
              placeholder="15000"
              value={amount}
              onChangeText={(value) => setAmount(value.replace(/[^0-9]/g, ''))}
              keyboardType="number-pad"
              icon="cash-outline"
            />

            <Text style={styles.fieldLabel}>Paid with</Text>
            <View style={styles.methods}>
              {METHODS.map((entry) => (
                <Pressable
                  key={entry.value}
                  onPress={() => setMethod(entry.value)}
                  style={[styles.method, method === entry.value && styles.methodActive]}
                >
                  <Text
                    style={[
                      styles.methodText,
                      method === entry.value && styles.methodTextActive,
                    ]}
                  >
                    {entry.label}
                  </Text>
                </Pressable>
              ))}
            </View>

            <Input
              label="Transaction reference"
              placeholder="The reference on your receipt"
              value={reference}
              onChangeText={setReference}
              icon="receipt-outline"
              autoCapitalize="characters"
            />

            <Pressable onPress={pickReceipt} style={styles.upload}>
              <Ionicons
                name={receipt ? 'checkmark-circle' : 'cloud-upload-outline'}
                size={20}
                color={receipt ? colors.green : colors.gold}
              />
              <Text style={styles.uploadText}>
                {receipt ? receipt.fileName ?? 'Receipt attached' : 'Attach receipt photo'}
              </Text>
            </Pressable>

            <Button
              label="Submit for verification"
              onPress={submit}
              loading={requestTopUp.isPending}
            />
            <Button label="Cancel" variant="ghost" onPress={() => setSheetOpen(false)} />
          </ScrollView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function LedgerRow({ row }: { row: WalletTransaction }) {
  const isIn = row.direction === 'in';
  return (
    <View style={styles.row}>
      <View style={[styles.rowIcon, isIn ? styles.rowIconIn : styles.rowIconOut]}>
        <Ionicons
          name={isIn ? 'arrow-down' : 'arrow-up'}
          size={14}
          color={isIn ? colors.green : colors.red}
        />
      </View>
      <View style={styles.rowBody}>
        <Text style={styles.rowTitle}>{row.type_label}</Text>
        <Text style={styles.rowMeta} numberOfLines={1}>
          {row.description || row.reference || timeAgo(row.created_at)}
        </Text>
      </View>
      <View style={styles.rowRight}>
        <Text style={[styles.rowAmount, isIn ? styles.amountIn : styles.amountOut]}>
          {isIn ? '+' : '−'}
          {formatPKR(row.amount)}
        </Text>
        <Text style={styles.rowBalance}>{formatPKR(row.balance_after)}</Text>
      </View>
    </View>
  );
}

function TopUpRow({ row }: { row: TopUpRequest }) {
  const tone =
    row.status === 'APPROVED'
      ? styles.statusApproved
      : row.status === 'REJECTED'
        ? styles.statusRejected
        : styles.statusPending;

  return (
    <View style={styles.row}>
      <View style={styles.rowBody}>
        <Text style={styles.rowTitle}>{formatPKR(row.amount)}</Text>
        <Text style={styles.rowMeta}>
          {row.transaction_reference} · {formatDate(row.created_at)}
        </Text>
        {row.admin_note ? (
          <Text style={styles.adminNote}>{row.admin_note}</Text>
        ) : null}
      </View>
      <Text style={[styles.status, tone]}>{row.status_label}</Text>
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
  headerSpacer: { width: 24 },
  content: { padding: spacing.xl, paddingBottom: spacing.huge },
  balanceCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderMid,
    padding: spacing.xl,
    marginBottom: spacing.lg,
    alignItems: 'center',
  },
  balanceLabel: { ...typography.caption, color: colors.sub },
  balance: { ...typography.display, color: colors.gold, marginVertical: spacing.sm },
  balanceMeta: { flexDirection: 'row', gap: spacing.xl },
  balanceMetaText: { ...typography.tiny, color: colors.dim },
  pending: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  pendingText: { ...typography.caption, color: colors.amber, flex: 1 },
  sectionTitle: {
    ...typography.caption,
    color: colors.sub,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.xxl,
    marginBottom: spacing.sm,
  },
  hint: { ...typography.caption, color: colors.dim },
  ledger: {
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
    padding: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowIconIn: { backgroundColor: colors.greenDim },
  rowIconOut: { backgroundColor: colors.redDim },
  rowBody: { flex: 1 },
  rowTitle: { ...typography.caption, color: colors.text, fontWeight: '600' },
  rowMeta: { ...typography.tiny, color: colors.sub, marginTop: 1 },
  adminNote: { ...typography.tiny, color: colors.amber, marginTop: 2 },
  rowRight: { alignItems: 'flex-end' },
  rowAmount: { ...typography.caption, fontWeight: '700' },
  amountIn: { color: colors.green },
  amountOut: { color: colors.red },
  rowBalance: { ...typography.tiny, color: colors.dim, marginTop: 1 },
  status: { ...typography.tiny, fontWeight: '700' },
  statusPending: { color: colors.amber },
  statusApproved: { color: colors.green },
  statusRejected: { color: colors.red },
  backdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '88%',
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
  methods: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  method: {
    flex: 1,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    alignItems: 'center',
  },
  methodActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  methodText: { ...typography.tiny, color: colors.sub, fontWeight: '600' },
  methodTextActive: { color: colors.bg },
  upload: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.borderMid,
    marginBottom: spacing.md,
  },
  uploadText: { ...typography.caption, color: colors.text },
});
