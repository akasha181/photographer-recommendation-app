import { Ionicons } from '@expo/vector-icons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React from 'react';

import { DashboardScreen } from '../features/dashboard/screens/DashboardScreen';
import { BookingDetailScreen } from '../features/bookings/screens/BookingDetailScreen';
import { BookingsScreen } from '../features/bookings/screens/BookingsScreen';
import { RequestsScreen } from '../features/bookings/screens/RequestsScreen';
import { PortfolioScreen } from '../features/portfolio/screens/PortfolioScreen';
import { ProfileScreen } from '../features/profile/screens/ProfileScreen';
import { WalletScreen } from '../features/profile/screens/WalletScreen';
import { WishlistScreen } from '../features/profile/screens/WishlistScreen';
import { ProductDetailScreen } from '../features/shop/screens/ProductDetailScreen';
import { PurchasesScreen } from '../features/shop/screens/PurchasesScreen';
import { SellerProductsScreen } from '../features/shop/screens/SellerProductsScreen';
import { colors } from '../theme';
import { useTabBarOptions } from './tabBarStyle';

export type PhotographerTabParams = {
  Dashboard: undefined;
  Requests: undefined;
  Jobs: undefined;
  Portfolio: undefined;
  Profile: undefined;
};

/**
 * Selling lives inside the Profile screen rather than in a sixth tab.
 *
 * Six bottom tabs is past the point where labels start truncating on a small
 * Android device, and a photographer opens their catalogue far less often
 * than they check requests. The route still exists in this stack, so it is
 * one tap from Profile and deep-linkable.
 */
export type PhotographerStackParams = {
  Tabs: undefined;
  BookingDetail: { bookingId: number };
  SellerProducts: undefined;
  ProductDetail: { slug: string };
  Purchases: undefined;
  Wallet: undefined;
  Wishlist: undefined;
};

const Tab = createBottomTabNavigator<PhotographerTabParams>();
const Stack = createNativeStackNavigator<PhotographerStackParams>();

const ICONS: Record<keyof PhotographerTabParams, keyof typeof Ionicons.glyphMap> = {
  Dashboard: 'stats-chart',
  Requests: 'notifications',
  Jobs: 'calendar',
  Portfolio: 'images',
  Profile: 'person',
};

function PhotographerTabs({ navigation }: any) {
  const tabBarOptions = useTabBarOptions();

  const openBooking = (bookingId: number) =>
    navigation.navigate('BookingDetail', { bookingId });

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
      <Tab.Screen name="Dashboard">
        {() => <DashboardScreen />}
      </Tab.Screen>

      <Tab.Screen name="Requests">
        {() => <RequestsScreen onOpenBooking={openBooking} />}
      </Tab.Screen>

      <Tab.Screen name="Jobs">
        {() => (
          <BookingsScreen perspective="photographer" onOpenBooking={openBooking} />
        )}
      </Tab.Screen>

      <Tab.Screen name="Portfolio">
        {() => <PortfolioScreen />}
      </Tab.Screen>

      <Tab.Screen name="Profile">
        {({ navigation: tabNav }) => (
          <ProfileScreen
            onOpenWallet={() => navigation.navigate('Wallet')}
            onOpenWishlist={() => navigation.navigate('Wishlist')}
            onOpenPurchases={() => navigation.navigate('Purchases')}
            onOpenBookings={() => tabNav.navigate('Jobs')}
            onOpenSellerProducts={() => navigation.navigate('SellerProducts')}
          />
        )}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

export function PhotographerNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.bg },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="Tabs" component={PhotographerTabs} />

      <Stack.Screen name="BookingDetail">
        {({ route, navigation }) => (
          <BookingDetailScreen
            bookingId={route.params.bookingId}
            perspective="photographer"
            onBack={() =>
              navigation.canGoBack() ? navigation.goBack() : navigation.navigate('Tabs')
            }
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="SellerProducts">
        {({ navigation }) => (
          <SellerProductsScreen
            onBack={() => navigation.goBack()}
            onOpenProduct={(slug) => navigation.navigate('ProductDetail', { slug })}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="ProductDetail">
        {({ route, navigation }) => (
          <ProductDetailScreen
            slug={route.params.slug}
            onBack={() => navigation.goBack()}
            // A photographer browsing the shop is a buyer like any other, but
            // there is no Cart tab on this side — send them to the wallet,
            // which is where the balance they would spend actually lives.
            onOpenCart={() => navigation.navigate('Wallet')}
            onTopUp={() => navigation.navigate('Wallet')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Purchases">
        {({ navigation }) => <PurchasesScreen onBack={() => navigation.goBack()} />}
      </Stack.Screen>

      <Stack.Screen name="Wallet">
        {({ navigation }) => <WalletScreen onBack={() => navigation.goBack()} />}
      </Stack.Screen>

      <Stack.Screen name="Wishlist">
        {({ navigation }) => (
          <WishlistScreen
            onBack={() => navigation.goBack()}
            // Photographers do not have the buyer's photographer-detail route,
            // so a saved photographer is a dead tap here. Products are not.
            onOpenPhotographer={() => undefined}
            onOpenProduct={(slug) => navigation.navigate('ProductDetail', { slug })}
          />
        )}
      </Stack.Screen>
    </Stack.Navigator>
  );
}
