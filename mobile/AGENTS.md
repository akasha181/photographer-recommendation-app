# Expo SDK 54

This project is pinned to **Expo SDK 54** (`expo@~54.0.36`, React Native 0.81,
React 19.1).

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/
before writing any code. Do NOT follow SDK 55/56/57 documentation — APIs,
config-plugin availability and package versions differ between SDKs.

## Why SDK 54 and not the latest

Expo Go supports exactly one SDK version at a time, and the build available on
the Play Store for this project's target devices is the SDK 54 client.
Scaffolding on SDK 57 produced:

    ERROR  Project is incompatible with this version of Expo Go

Do not run `npx expo install expo@latest` or `--fix` against a newer SDK
without first confirming the Expo Go build on the test device supports it.

## SDK 54 gotchas already handled here

* `expo-image` ships **no config plugin** in SDK 54 — it must not appear in
  `app.json` → `plugins`. (It does in later SDKs, which is why the scaffold
  added it.)
* `react-native-reanimated@4` requires `react-native-worklets` as a direct
  dependency **and** `react-native-worklets/plugin` as the last entry in
  `babel.config.js`.

## Version alignment

After changing any Expo package, run:

    npx expo install --check     # report drift
    npx expo install --fix       # realign to the SDK
    npx tsc --noEmit             # typecheck
