import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

const KEY = 'access_token';

export async function saveToken(token: string) {
  if (Platform.OS === 'web') return localStorage.setItem(KEY, token);
  await SecureStore.setItemAsync(KEY, token);
}

export async function loadToken(): Promise<string | null> {
  if (Platform.OS === 'web') return localStorage.getItem(KEY);
  return SecureStore.getItemAsync(KEY);
}

export async function clearToken() {
  if (Platform.OS === 'web') return localStorage.removeItem(KEY);
  await SecureStore.deleteItemAsync(KEY);
}
