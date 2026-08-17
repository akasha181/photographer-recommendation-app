import { Ionicons } from '@expo/vector-icons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React from 'react';

import { BookingDetailScreen } from '../features/bookings/screens/BookingDetailScreen';
import { BookingsScreen } from '../features/bookings/screens/BookingsScreen';
import { RequestsScreen } from '../features/bookings/screens/RequestsScreen';
import { ChatScreen } from '../features/chat/screens/ChatScreen';
import { ConversationsScreen } from '../features/chat/screens/ConversationsScreen';
import { NewChatScreen } from '../features/chat/screens/NewChatScreen';
import { NotificationSettingsScreen } from '../features/notifications/screens/NotificationSettingsScreen';
import { NotificationsScreen } from '../features/notifications/screens/NotificationsScreen';
import { ReceivedReviewsScreen } from '../features/reviews/screens/ReceivedReviewsScreen';
import { DashboardScreen } from '../features/photographer/screens/DashboardScreen';
import { EditProfileScreen } from '../features/photographer/screens/EditProfileScreen';
import { MyCalendarScreen } from '../features/photographer/screens/MyCalendarScreen';
import { MyPortfolioScreen } from '../features/photographer/screens/MyPortfolioScreen';
import { MyServicesScreen } from '../features/photographer/screens/MyServicesScreen';
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
  MyServices: undefined;
  MyCalendar: undefined;
  EditProfile: undefined;
  /** Module 9 — the reviews this photographer received, and their replies. */
  ReceivedReviews: undefined;
  // ─── Modules 12 & 13 ────────────────────────────────────────────────────
  Notifications: undefined;
  NotificationSettings: undefined;
  Conversations: undefined;
  NewChat: undefined;
  Chat: {
    conversationId: number;
    withUserId?: number;
    bookingId?: number;
    title?: string;
  };
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
        {({ navigation: tabNav }) => (
          <DashboardScreen
            onOpenRequests={() => tabNav.navigate('Requests')}
            onOpenJobs={() => tabNav.navigate('Jobs')}
            onOpenServices={() => navigation.navigate('MyServices')}
            onOpenNotifications={() => navigation.navigate('Notifications')}
            onOpenMessages={() => navigation.navigate('Conversations')}
            onOpenReviews={() => navigation.navigate('ReceivedReviews')}
          />
        )}
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
        {() => <MyPortfolioScreen />}
      </Tab.Screen>

      <Tab.Screen name="Profile">
        {({ navigation: tabNav }) => (
          <ProfileScreen
            onOpenWallet={() => navigation.navigate('Wallet')}
            onOpenWishlist={() => navigation.navigate('Wishlist')}
            onOpenPurchases={() => navigation.navigate('Purchases')}
            onOpenBookings={() => tabNav.navigate('Jobs')}
            onOpenSellerProducts={() => navigation.navigate('SellerProducts')}
            onOpenServices={() => navigation.navigate('MyServices')}
            onOpenCalendar={() => navigation.navigate('MyCalendar')}
            onEditProfile={() => navigation.navigate('EditProfile')}
            onOpenReviews={() => navigation.navigate('ReceivedReviews')}
            onOpenMessages={() => navigation.navigate('Conversations')}
            onOpenNotifications={() => navigation.navigate('Notifications')}
            onOpenNotificationSettings={() =>
              navigation.navigate('NotificationSettings')
            }
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
            // No `onWriteReview` here: only the buyer may review a shoot (see
            // docs/01 §11.3), so the server never offers the action to this side
            // and the button is filtered out rather than shown and refused.
            onOpenChat={(booking) =>
              navigation.navigate('Chat', {
                conversationId: 0,
                withUserId: booking.buyer.user_id,
                bookingId: booking.id,
                title: booking.buyer.name,
              })
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

      {/* ─── Module 5 — the photographer's own studio ─────────────────── */}
      <Stack.Screen name="MyServices">
        {({ navigation }) => <MyServicesScreen onBack={() => navigation.goBack()} />}
      </Stack.Screen>

      <Stack.Screen name="MyCalendar">
        {({ navigation }) => <MyCalendarScreen onBack={() => navigation.goBack()} />}
      </Stack.Screen>

      <Stack.Screen name="EditProfile">
        {({ navigation }) => <EditProfileScreen onBack={() => navigation.goBack()} />}
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

      {/* ─── Module 9 — reviews received ─────────────────────────────────── */}
      <Stack.Screen name="ReceivedReviews">
        {({ navigation }) => (
          <ReceivedReviewsScreen onBack={() => navigation.goBack()} />
        )}
      </Stack.Screen>

      {/* ─── Modules 12 & 13 — notifications and chat ────────────────────── */}
      <Stack.Screen name="Notifications">
        {({ navigation }) => (
          <NotificationsScreen
            onBack={() => navigation.goBack()}
            onOpenBooking={(bookingId) =>
              navigation.navigate('BookingDetail', { bookingId })
            }
            onOpenChat={(conversationId) =>
              navigation.navigate('Chat', { conversationId })
            }
            onOpenReviews={() => navigation.navigate('ReceivedReviews')}
            onOpenProduct={(slug) => navigation.navigate('ProductDetail', { slug })}
            onOpenPreferences={() => navigation.navigate('NotificationSettings')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="NotificationSettings">
        {({ navigation }) => (
          <NotificationSettingsScreen onBack={() => navigation.goBack()} />
        )}
      </Stack.Screen>

      <Stack.Screen name="Conversations">
        {({ navigation }) => (
          <ConversationsScreen
            onBack={() => navigation.goBack()}
            onOpenThread={(conversationId, title) =>
              navigation.navigate('Chat', { conversationId, title })
            }
            onNewMessage={() => navigation.navigate('NewChat')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="NewChat">
        {({ navigation }) => (
          <NewChatScreen
            onBack={() => navigation.goBack()}
            onOpenThread={(conversationId, title) =>
              navigation.replace('Chat', { conversationId, title })
            }
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Chat">
        {({ route, navigation }) => (
          <ChatScreen
            conversationId={route.params.conversationId}
            startWith={
              route.params.withUserId
                ? {
                    userId: route.params.withUserId,
                    bookingId: route.params.bookingId,
                  }
                : undefined
            }
            title={route.params.title}
            onBack={() => navigation.goBack()}
            onOpenBooking={(bookingId) =>
              navigation.navigate('BookingDetail', { bookingId })
            }
          />
        )}
      </Stack.Screen>
    </Stack.Navigator>
  );
}
