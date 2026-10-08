import { Platform } from 'react-native';

// Android emulator reaches your computer at 10.0.2.2.
// On a real phone set EXPO_PUBLIC_API_URL=http://<your-computer-LAN-IP>:8000 in .env
export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  (Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000');

export type User = {
  id: number;
  username: string;
  email: string;
  profile_pic?: string | null;
};

export type Photo = { uri: string; name: string; type: string };

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: any) => d.msg).join('\n');
  } catch {}
  return 'Something went wrong. Try again.';
}

async function request(path: string, init: RequestInit) {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'ngrok-skip-browser-warning': 'true', ...(init.headers as any) },
    });
  } catch (e: any) {
    throw new Error(`Can't reach the server at ${API_URL} (${e?.message ?? 'network error'}).`);
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export function loginRequest(username: string, password: string) {
  return request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }).toString(),
  }) as Promise<{ access_token: string; token_type: string }>;
}

export async function signupRequest(f: {
  username: string;
  email: string;
  password: string;
  photo?: Photo | null;
}) {
  const form = new FormData();
  form.append('username', f.username);
  form.append('email', f.email);
  form.append('password', f.password);
  if (f.photo) {
    if (Platform.OS === 'web') {
      const blob = await (await fetch(f.photo.uri)).blob();
      form.append('profile_pic', blob, f.photo.name);
    } else {
      form.append('profile_pic', { uri: f.photo.uri, name: f.photo.name, type: f.photo.type } as any);
    }
  }
  // Don't set Content-Type: fetch adds the multipart boundary itself.
  return request('/auth/signup', { method: 'POST', body: form }) as Promise<User>;
}

export function fetchMe(token: string) {
  return request('/auth/me', { headers: { Authorization: `Bearer ${token}` } }) as Promise<User>;
}

// ---------- Materials ----------
export type Material = {
  id: number;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  created_at: string;
};

async function appendFile(form: FormData, field: string, file: Photo) {
  if (Platform.OS === 'web') {
    const blob = await (await fetch(file.uri)).blob();
    form.append(field, blob, file.name);
  } else {
    form.append(field, { uri: file.uri, name: file.name, type: file.type } as any);
  }
}

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

export async function uploadMaterial(token: string, file: Photo) {
  const form = new FormData();
  await appendFile(form, 'file', file);
  return request('/materials/upload', { method: 'POST', headers: auth(token), body: form }) as Promise<Material>;
}

export function listMaterials(token: string) {
  return request('/materials', { headers: auth(token) }) as Promise<Material[]>;
}

export async function deleteMaterial(token: string, id: number) {
  await request(`/materials/${id}`, { method: 'DELETE', headers: auth(token) });
}
