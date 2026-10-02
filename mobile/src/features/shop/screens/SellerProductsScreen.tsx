import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatCount, formatPKR } from '../../../utils/format';
import type { SellerProduct } from '../../../types/models';
import { ProductThumb } from '../components/ProductThumb';
import { useCreateSellerProduct, useSellerProducts, useSellerSummary } from '../hooks/useShop';

const PRODUCT_TYPES = [
  { value: 'CAMERA_ACCESSORY', label: 'Camera Gear' },
  { value: 'MOBILE_ACCESSORY', label: 'Mobile Gear' },
  { value: 'LENS', label: 'Lenses' },
  { value: 'LIGHTING_AUDIO', label: 'Lighting & Mics' },
  { value: 'TRIPOD_GIMBAL', label: 'Tripods & Gimbals' },
  { value: 'OTHER', label: 'Presets & Other' },
];

export function SellerProductsScreen({
  onBack,
  onOpenProduct,
}: {
  onBack: () => void;
  onOpenProduct: (slug: string) => void;
}) {
  const products = useSellerProducts();
  const summary = useSellerSummary();
  const createProduct = useCreateSellerProduct();

  // Add product modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [title, setTitle] = useState('');
  const [price, setPrice] = useState('');
  const [comparePrice, setComparePrice] = useState('');
  const [description, setDescription] = useState('');
  const [productType, setProductType] = useState('CAMERA_ACCESSORY');
  const [selectedImage, setSelectedImage] = useState<ImagePicker.ImagePickerAsset | null>(null);

  const pickImage = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        'Gallery permission needed',
        'Please allow gallery access to select a product photo.',
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [4, 3],
      quality: 0.8,
    });

    if (!result.canceled && result.assets.length > 0) {
      setSelectedImage(result.assets[0]);
    }
  };

  const handleCreate = () => {
    if (!title.trim()) {
      Alert.alert('Required field', 'Please enter a title for your product.');
      return;
    }
    const numPrice = Number(price);
    if (!numPrice || numPrice <= 0) {
      Alert.alert('Required field', 'Please enter a valid price in PKR.');
      return;
    }

    createProduct.mutate(
      {
        title: title.trim(),
        price: numPrice,
        compare_at_price: comparePrice ? Number(comparePrice) : undefined,
        description: description.trim(),
        product_type: productType,
        thumbnail: selectedImage
          ? {
              uri: selectedImage.uri,
              name: selectedImage.fileName ?? `product-${Date.now()}.jpg`,
              type: selectedImage.mimeType ?? 'image/jpeg',
            }
          : undefined,
      },
      {
        onSuccess: () => {
          setShowAddModal(false);
          setTitle('');
          setPrice('');
          setComparePrice('');
          setDescription('');
          setSelectedImage(null);
          Alert.alert('Success', 'Your product has been listed for sale!');
        },
        onError: (err) => {
          Alert.alert('Could not list product', (err as ApiError)?.message ?? 'Please try again.');
        },
      },
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>My products</Text>
        <Pressable
          onPress={() => setShowAddModal(true)}
          hitSlop={10}
          accessibilityLabel="Add product"
          style={styles.addButton}
        >
          <Ionicons name="add" size={24} color={colors.bg} />
        </Pressable>
      </View>

      {products.isLoading ? (
        <LoadingState label="Loading your catalogue…" />
      ) : products.isError ? (
        <ErrorState
          message={(products.error as ApiError)?.message}
          onRetry={() => products.refetch()}
        />
      ) : (
        <FlatList
          data={products.data ?? []}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={products.data?.length ? styles.list : styles.listEmpty}
          refreshControl={
            <RefreshControl
              refreshing={products.isRefetching}
              onRefresh={() => products.refetch()}
              tintColor={colors.gold}
            />
          }
          ListHeaderComponent={
            summary.data ? (
              <View style={styles.summary}>
                <View style={styles.summaryRow}>
                  <Metric
                    value={formatPKR(summary.data.net_earnings)}
                    label="Net earnings"
                    highlight
                  />
                  <Metric
                    value={formatCount(summary.data.sales_count)}
                    label="Sales"
                  />
                </View>
                <View style={styles.summaryRow}>
                  <Metric
                    value={String(summary.data.products_live)}
                    label="Live listings"
                  />
                  <Metric
                    value={formatPKR(summary.data.gross_revenue)}
                    label="Gross revenue"
                  />
                </View>
                <Text style={styles.summaryNote}>
                  Earnings are credited to your wallet as each sale completes.
                </Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <SellerRow product={item} onPress={() => onOpenProduct(item.slug)} />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="pricetags-outline"
              title="No products yet"
              detail="Tap the '+' button above to list presets, camera accessories, or gear for sale."
            />
          }
        />
      )}

      {/* ─── Add Product Modal ────────────────────────────────────────── */}
      <Modal visible={showAddModal} animationType="slide" transparent>
        <SafeAreaView style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>List product for sale</Text>
              <Pressable onPress={() => setShowAddModal(false)} hitSlop={10}>
                <Ionicons name="close" size={24} color={colors.sub} />
              </Pressable>
            </View>

            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.formScroll}>
              {/* Image Picker */}
              <Text style={styles.fieldLabel}>Product Image</Text>
              <Pressable onPress={pickImage} style={styles.imagePicker}>
                {selectedImage ? (
                  <Image source={{ uri: selectedImage.uri }} style={styles.selectedImagePreview} contentFit="cover" />
                ) : (
                  <View style={styles.pickerPlaceholder}>
                    <Ionicons name="image-outline" size={32} color={colors.gold} />
                    <Text style={styles.pickerText}>Select photo from gallery</Text>
                  </View>
                )}
              </Pressable>

              <Input
                label="Product title"
                placeholder="e.g. Vintage Lightroom Presets"
                value={title}
                onChangeText={setTitle}
              />

              <View style={styles.priceRow}>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Price (PKR)"
                    placeholder="2500"
                    keyboardType="numeric"
                    value={price}
                    onChangeText={setPrice}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Original price (optional)"
                    placeholder="3500"
                    keyboardType="numeric"
                    value={comparePrice}
                    onChangeText={setComparePrice}
                  />
                </View>
              </View>

              <Text style={styles.fieldLabel}>Category</Text>
              <View style={styles.typeChips}>
                {PRODUCT_TYPES.map((t) => {
                  const active = productType === t.value;
                  return (
                    <Pressable
                      key={t.value}
                      onPress={() => setProductType(t.value)}
                      style={[styles.typeChip, active && styles.typeChipActive]}
                    >
                      <Text style={[styles.typeChipText, active && styles.typeChipTextActive]}>
                        {t.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              <Input
                label="Description"
                placeholder="Describe what is included, features, or gear compatibility…"
                multiline
                value={description}
                onChangeText={setDescription}
              />

              <Button
                label="List Product"
                onPress={handleCreate}
                loading={createProduct.isPending}
                size="lg"
              />
            </ScrollView>
          </View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

function SellerRow({
  product,
  onPress,
}: {
  product: SellerProduct;
  onPress: () => void;
}) {
  const live = product.is_published && product.is_approved;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
      accessibilityRole="button"
      accessibilityLabel={`${product.title}, ${formatPKR(product.price)}`}
    >
      <ProductThumb
        uri={product.thumbnail_url}
        title={product.title}
        style={styles.thumb}
      />
      <View style={styles.rowBody}>
        <Text style={styles.rowTitle} numberOfLines={1}>
          {product.title}
        </Text>
        <Text style={styles.rowMeta}>
          {formatCount(product.sales_count)} sales · {product.product_type}
        </Text>
      </View>
      <View style={styles.rowRight}>
        <Text style={styles.rowPrice}>{formatPKR(product.price)}</Text>
        <Text style={[styles.rowStatus, live ? styles.statusLive : styles.statusDraft]}>
          {live ? 'Live' : 'Draft'}
        </Text>
      </View>
    </Pressable>
  );
}

function Metric({
  value,
  label,
  highlight,
}: {
  value: string;
  label: string;
  highlight?: boolean;
}) {
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, highlight && styles.metricHighlight]} numberOfLines={1}>
        {value}
      </Text>
      <Text style={styles.metricLabel}>{label}</Text>
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
  },
  headerTitle: { ...typography.h3, color: colors.text },
  addButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
  },
  list: { padding: spacing.xl, paddingTop: 0 },
  listEmpty: { flexGrow: 1 },
  summary: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  summaryRow: { flexDirection: 'row', marginBottom: spacing.md },
  metric: { flex: 1 },
  metricValue: { ...typography.h3, color: colors.text },
  metricHighlight: { color: colors.gold },
  metricLabel: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  summaryNote: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  rowPressed: { backgroundColor: colors.cardHover },
  thumb: { width: 56, height: 44, borderRadius: radius.sm },
  rowBody: { flex: 1 },
  rowTitle: { ...typography.caption, color: colors.text, fontWeight: '600' },
  rowMeta: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  rowRight: { alignItems: 'flex-end' },
  rowPrice: { ...typography.caption, color: colors.gold, fontWeight: '700' },
  rowStatus: { ...typography.tiny, marginTop: 2 },
  statusLive: { color: colors.green },
  statusDraft: { color: colors.dim },

  // Modal styles
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    maxHeight: '90%',
    padding: spacing.xl,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  modalTitle: { ...typography.h2, color: colors.text },
  formScroll: { gap: spacing.md, paddingBottom: spacing.xxxl },
  fieldLabel: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  imagePicker: {
    height: 140,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: 'dashed',
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pickerPlaceholder: { alignItems: 'center', gap: spacing.xs },
  pickerText: { ...typography.caption, color: colors.sub },
  selectedImagePreview: { width: '100%', height: '100%' },
  priceRow: { flexDirection: 'row', gap: spacing.md },
  typeChips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.xs },
  typeChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  typeChipActive: { backgroundColor: colors.goldDim, borderColor: colors.gold },
  typeChipText: { ...typography.tiny, color: colors.sub },
  typeChipTextActive: { color: colors.gold, fontWeight: '700' },
});
