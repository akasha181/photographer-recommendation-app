import { Ionicons } from '@expo/vector-icons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React from 'react';

import { BookingDetailScreen } from '../features/bookings/screens/BookingDetailScreen';
import { BookingsScreen } from '../features/bookings/screens/BookingsScreen';
import { CreateBookingScreen } from '../features/bookings/screens/CreateBookingScreen';
import { ExploreScreen } from '../features/explore/screens/ExploreScreen';
import { HomeScreen } from '../features/explore/screens/HomeScreen';
import { PhotographerDetailScreen } from '../features/photographer/screens/PhotographerDetailScreen';
import { ProfileScreen } from '../features/profile/screens/ProfileScreen';
import { WalletScreen } from '../features/profile/screens/WalletScreen';
import { WishlistScreen } from '../features/profile/screens/WishlistScreen';
import { CartScreen } from '../features/shop/screens/CartScreen';
import { ProductDetailScreen } from '../features/shop/screens/ProductDetailScreen';
import { PurchasesScreen } from '../features/shop/screens/PurchasesScreen';
import { ShopScreen } from '../features/shop/screens/ShopScreen';
import { colors } from '../theme';
import { useTabBarOptions } from './tabBarStyle';

export type BuyerTabParams = {
  Home: undefined;
  Explore: { category?: string } | undefined;
  Bookings: undefined;
  Shop: undefined;
  Profile: undefined;
};

/**
 * Detail, form and checkout screens live in a STACK ABOVE the tabs.
 *
 * If they were tab screens the bottom bar would stay visible and the sticky
 * action bars ("Book now", "Pay from wallet") would sit on top of it. Pushing
 * them over the whole tab navigator also means the same product or booking is
 * reachable from several tabs and always renders the same screen with a
 * working back button.
 */
export type BuyerStackParams = {
  Tabs: undefined;
  PhotographerDetail: { photographerId: number };
  CreateBooking: { photographerId: number; serviceId?: number };
  BookingDetail: { bookingId: number };
  ProductDetail: { slug: string };
  Cart: undefined;
  Purchases: undefined;
  Wallet: undefined;
  Wishlist: undefined;
};

const Tab = createBottomTabNavigator<BuyerTabParams>();
const Stack = createNativeStackNavigator<BuyerStackParams>();

const ICONS: Record<keyof BuyerTabParams, keyof typeof Ionicons.glyphMap> = {
  Home: 'home',
  Explore: 'search',
  Bookings: 'calendar',
  Shop: 'bag-handle',
  Profile: 'person',
};

function BuyerTabs({ navigation }: any) {
  const tabBarOptions = useTabBarOptions();

  const openPhotographer = (photographerId: number) =>
    navigation.navigate('PhotographerDetail', { photographerId });
  const openBooking = (bookingId: number) =>
    navigation.navigate('BookingDetail', { bookingId });
  const openProduct = (slug: string) => navigation.navigate('ProductDetail', { slug });

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        ...tabBarOptions,
        tabBarIcon: ({ color, size, focused }) => (
          <Ionicons
            name={
              focused
                ? ICONS[route.name]
                : (`${ICONS[route.name]}-outline` as keyof typeof Ionicons.glyphMap)
            }
            size={size - 2}
            color={color}
          />
        ),
      })}
    >
      <Tab.Screen name="Home">
        {({ navigation: tabNav }) => (
          <HomeScreen
            onOpenPhotographer={openPhotographer}
            onOpenCategory={(category) => tabNav.navigate('Explore', { category })}
            onOpenSearch={() => tabNav.navigate('Explore')}
          />
        )}
      </Tab.Screen>

      <Tab.Screen name="Explore">
        {({ route }) => (
          <ExploreScreen
            onOpenPhotographer={openPhotographer}
            initialCategory={route.params?.category}
          />
        )}
      </Tab.Screen>

      <Tab.Screen name="Bookings">
        {({ navigation: tabNav }) => (
          <BookingsScreen
            perspective="buyer"
            onOpenBooking={openBooking}
            onBrowse={() => tabNav.navigate('Explore')}
          />
        )}
      </Tab.Screen>

      <Tab.Screen name="Shop">
        {() => (
          <ShopScreen
            onOpenProduct={openProduct}
            onOpenCart={() => navigation.navigate('Cart')}
          />
        )}
      </Tab.Screen>

      <Tab.Screen name="Profile">
        {({ navigation: tabNav }) => (
          <ProfileScreen
            onOpenWallet={() => navigation.navigate('Wallet')}
            onOpenWishlist={() => navigation.navigate('Wishlist')}
            onOpenPurchases={() => navigation.navigate('Purchases')}
            onOpenBookings={() => tabNav.navigate('Bookings')}
          />
        )}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

export function BuyerNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.bg },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="Tabs" component={BuyerTabs} />

      {/* ─── Booking flow ────────────────────────────────────────────────── */}
      <Stack.Screen name="PhotographerDetail">
        {({ route, navigation }) => (
          <PhotographerDetailScreen
            photographerId={route.params.photographerId}
            onBack={() => navigation.goBack()}
            onBook={(serviceId) =>
              navigation.navigate('CreateBooking', {
                photographerId: route.params.photographerId,
                serviceId,
              })
            }
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="CreateBooking">
        {({ route, navigation }) => (
          <CreateBookingScreen
            photographerId={route.params.photographerId}
            initialServiceId={route.params.serviceId}
            onBack={() => navigation.goBack()}
            // `replace`, not `navigate`: once the request is sent, backing up
            // into a form that would create a second booking is exactly the
            // mistake the Idempotency-Key exists to catch. Better not to
            // offer the route at all.
            onCreated={(bookingId) => navigation.replace('BookingDetail', { bookingId })}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="BookingDetail">
        {({ route, navigation }) => (
          <BookingDetailScreen
            bookingId={route.params.bookingId}
            perspective="buyer"
            onBack={() =>
              navigation.canGoBack() ? navigation.goBack() : navigation.navigate('Tabs')
            }
          />
        )}
      </Stack.Screen>

      {/* ─── Shop flow ───────────────────────────────────────────────────── */}
      <Stack.Screen name="ProductDetail">
        {({ route, navigation }) => (
          <ProductDetailScreen
            slug={route.params.slug}
            onBack={() => navigation.goBack()}
            onOpenCart={() => navigation.navigate('Cart')}
            onTopUp={() => navigation.navigate('Wallet')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Cart">
        {({ navigation }) => (
          <CartScreen
            onBack={() => navigation.goBack()}
            onOpenProduct={(slug) => navigation.navigate('ProductDetail', { slug })}
            onTopUp={() => navigation.navigate('Wallet')}
            // Straight to the library after paying: the cart the buyer came
            // from is now empty, so returning to it would show an empty state
            // as the reward for a purchase.
            onPurchased={() => navigation.replace('Purchases')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Purchases">
        {({ navigation }) => <PurchasesScreen onBack={() => navigation.goBack()} />}
      </Stack.Screen>

      {/* ─── Profile flow ────────────────────────────────────────────────── */}
      <Stack.Screen name="Wallet">
        {({ navigation }) => <WalletScreen onBack={() => navigation.goBack()} />}
      </Stack.Screen>

      <Stack.Screen name="Wishlist">
        {({ navigation }) => (
          <WishlistScreen
            onBack={() => navigation.goBack()}
            onOpenPhotographer={(photographerId) =>
              navigation.navigate('PhotographerDetail', { photographerId })
            }
            onOpenProduct={(slug) => navigation.navigate('ProductDetail', { slug })}
          />
        )}
      </Stack.Screen>
    </Stack.Navigator>
  );
}
