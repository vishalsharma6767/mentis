import { Platform } from 'react-native';

const isWeb = Platform.OS === 'web';

export async function setItem(key: string, value: string): Promise<void> {
  if (isWeb) {
    localStorage.setItem(key, value);
  } else {
    const SecureStore = await import('expo-secure-store');
    await SecureStore.setItemAsync(key, value);
  }
}

export async function getItem(key: string): Promise<string | null> {
  if (isWeb) {
    return localStorage.getItem(key);
  } else {
    try {
      const SecureStore = await import('expo-secure-store');
      return await SecureStore.getItemAsync(key);
    } catch {
      return null;
    }
  }
}

export async function deleteItem(key: string): Promise<void> {
  if (isWeb) {
    localStorage.removeItem(key);
  } else {
    const SecureStore = await import('expo-secure-store');
    await SecureStore.deleteItemAsync(key);
  }
}
