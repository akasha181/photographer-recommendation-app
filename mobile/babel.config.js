/**
 * Babel configuration.
 *
 * `react-native-worklets/plugin` is REQUIRED by react-native-reanimated 4.
 * Reanimated runs animation callbacks on the UI thread, and the plugin is
 * what compiles those functions into worklets that can be shipped there.
 *
 * Without it, animations either silently fall back to the JS thread (janky)
 * or throw "Reanimated 2 failed to create a worklet" at runtime. React
 * Navigation's stack transitions depend on it, so this affects every screen
 * push in the app — not just code that uses Reanimated directly.
 *
 * It MUST be the last plugin in the list.
 */
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [],
  };
};
