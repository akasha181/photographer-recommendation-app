import { Image } from 'expo-image';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { avatarColor, initials } from '../../utils/format';
import { colors, radius, typography } from '../../theme';

interface Props {
  name: string;
  uri?: string | null;
  size?: number;
  verified?: boolean;
}

/**
 * Avatar with an initials fallback.
 *
 * Seeded photographers have no uploaded image, and a grid of identical
 * placeholder icons is unreadable. A deterministic colour + initials keeps
 * each person visually distinct without any asset.
 */
export function Avatar({ name, uri, size = 48, verified = false }: Props) {
  const dimension = { width: size, height: size, borderRadius: size / 2 };

  return (
    <View>
      {uri ? (
        <Image
          source={{ uri }}
          style={[styles.image, dimension]}
          contentFit="cover"
          // Cheap blurred placeholder while the real image decodes — avoids
          // the grey-box flash on a slow connection.
          placeholder={{ blurhash: 'L6Pj0^jE.AyE_3t7t7R**0o#DgR4' }}
          transition={180}
        />
      ) : (
        <View
          style={[styles.fallback, dimension, { backgroundColor: avatarColor(name) }]}
        >
          <Text style={[styles.initials, { fontSize: size * 0.36 }]}>
            {initials(name)}
          </Text>
        </View>
      )}

      {verified ? (
        <View
          style={[
            styles.badge,
            {
              width: size * 0.32,
              height: size * 0.32,
              borderRadius: size * 0.16,
            },
          ]}
        >
          <Text style={[styles.tick, { fontSize: size * 0.18 }]}>✓</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  image: { backgroundColor: colors.card },
  fallback: { alignItems: 'center', justifyContent: 'center' },
  initials: { ...typography.bodyBold, color: colors.white },
  badge: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    backgroundColor: colors.blue,
    borderWidth: 2,
    borderColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tick: { color: colors.white, fontWeight: '900' },
});
