import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, Image, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '@/context/AuthContext';
import { API_URL, deleteMaterial, listMaterials, Material, Photo, uploadMaterial } from '@/lib/api';
import { colors } from '@/lib/theme';

const OUTPUTS = ['Slides', 'Question paper', 'Quiz', 'Lesson plan', 'Summary notes', 'Flashcards'];

const formatSize = (b: number) =>
  b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`;

const extOf = (name: string) => (name.split('.').pop() ?? 'file').slice(0, 4).toUpperCase();

const confirm = async (msg: string) =>
  Platform.OS === 'web'
    ? window.confirm(msg)
    : new Promise<boolean>((resolve) =>
        Alert.alert('Delete material', msg, [
          { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
          { text: 'Delete', style: 'destructive', onPress: () => resolve(true) },
        ]),
      );

export default function Dashboard() {
  const { user, token, signOut } = useAuth();
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setMaterials(await listMaterials(token));
      setError('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const upload = async (files: Photo[]) => {
    if (!token || !files.length) return;
    setUploading(true);
    setError('');
    try {
      for (const f of files) {
        const m = await uploadMaterial(token, f);
        setMaterials((prev) => [m, ...prev]);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const pickDocuments = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: '*/*', multiple: true, copyToCacheDirectory: true });
    if (res.canceled) return;
    upload(res.assets.map((a) => ({ uri: a.uri, name: a.name, type: a.mimeType ?? 'application/octet-stream' })));
  };

  const toPhotos = (assets: ImagePicker.ImagePickerAsset[]): Photo[] =>
    assets.map((a, i) => ({
      uri: a.uri,
      name: a.fileName ?? `photo-${Date.now()}-${i}.jpg`,
      type: a.mimeType ?? 'image/jpeg',
    }));

  const pickPhotos = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsMultipleSelection: true, quality: 0.8 });
    if (!res.canceled) upload(toPhotos(res.assets));
  };

  const takePhoto = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return setError('Allow camera access in Settings to scan pages.');
    const res = await ImagePicker.launchCameraAsync({ quality: 0.8 });
    if (!res.canceled) upload(toPhotos(res.assets));
  };

  const remove = async (m: Material) => {
    if (!token || !(await confirm(`Delete "${m.filename}"?`))) return;
    try {
      await deleteMaterial(token, m.id);
      setMaterials((prev) => prev.filter((x) => x.id !== m.id));
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <View style={s.screen}>
      <StatusBar style="light" />
      <SafeAreaView edges={['top']} style={s.header}>
        <View style={s.row}>
          {user?.profile_pic ? (
            <Image source={{ uri: `${API_URL}${user.profile_pic}` }} style={s.avatar} />
          ) : (
            <View style={[s.avatar, s.fallback]}><Text style={s.initial}>{user?.username[0]?.toUpperCase()}</Text></View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={s.hello}>Hello, {user?.username}</Text>
            <Text style={s.sub}>What are we drafting today?</Text>
          </View>
          <Pressable onPress={signOut} style={s.logoutBtn}><Text style={s.logout}>Log out</Text></Pressable>
        </View>
      </SafeAreaView>

      <ScrollView
        style={s.body}
        contentContainerStyle={s.bodyContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.primary} />}
      >
        <View style={s.uploadCard}>
          <Text style={s.cardTitle}>Upload material</Text>
          <Text style={s.cardSub}>Add documents, slides, worksheets or photos of pages. You can pick several at once.</Text>
          <View style={s.actions}>
            <ActionButton label="Documents" onPress={pickDocuments} disabled={uploading} />
            <ActionButton label="Photos" onPress={pickPhotos} disabled={uploading} />
            {Platform.OS !== 'web' && <ActionButton label="Scan page" onPress={takePhoto} disabled={uploading} />}
          </View>
          {uploading && (
            <View style={s.uploading}><ActivityIndicator color={colors.primary} /><Text style={s.uploadingText}>Uploading…</Text></View>
          )}
          {!!error && <Text style={s.error}>{error}</Text>}
        </View>

        <Text style={s.section}>Create from your material</Text>
        <View style={s.grid}>
          {OUTPUTS.map((o) => (
            <View key={o} style={s.tile}>
              <Text style={s.tileText}>{o}</Text>
              <Text style={s.soon}>Coming soon</Text>
            </View>
          ))}
        </View>

        <Text style={s.section}>Your materials</Text>
        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />
        ) : materials.length === 0 ? (
          <Text style={s.empty}>Nothing here yet. Upload your first document above.</Text>
        ) : (
          materials.map((m) => (
            <View key={m.id} style={s.item}>
              <View style={s.badge}><Text style={s.badgeText}>{extOf(m.filename)}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={s.itemName} numberOfLines={1}>{m.filename}</Text>
                <Text style={s.itemMeta}>{formatSize(m.size_bytes)} • {new Date(m.created_at).toLocaleDateString()}</Text>
              </View>
              <Pressable onPress={() => remove(m)} hitSlop={10}><Text style={s.delete}>Delete</Text></Pressable>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function ActionButton({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[s.action, disabled && { opacity: 0.5 }]}>
      <Text style={s.actionText}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.primary },
  header: { paddingHorizontal: 20, paddingBottom: 40 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingTop: 12 },
  avatar: { width: 52, height: 52, borderRadius: 26, borderWidth: 2, borderColor: 'rgba(255,255,255,0.6)' },
  fallback: { backgroundColor: colors.paper, alignItems: 'center', justifyContent: 'center' },
  initial: { color: colors.primary, fontWeight: '800', fontSize: 22 },
  hello: { fontSize: 18, fontWeight: '700', color: '#fff' },
  sub: { color: '#DDD0FA', fontSize: 14 },
  logoutBtn: { backgroundColor: 'rgba(255,255,255,0.18)', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999 },
  logout: { color: '#fff', fontWeight: '700', fontSize: 13 },

  body: { flex: 1, backgroundColor: colors.paper, borderTopLeftRadius: 32, borderTopRightRadius: 32, marginTop: -24 },
  bodyContent: { padding: 22, paddingBottom: 48, width: '100%', maxWidth: 720, alignSelf: 'center' },

  uploadCard: { backgroundColor: colors.soft, borderRadius: 20, padding: 20, borderWidth: 1.5, borderColor: colors.border, borderStyle: 'dashed' },
  cardTitle: { fontSize: 20, fontWeight: '800', color: colors.text },
  cardSub: { color: colors.muted, marginTop: 4, marginBottom: 16, lineHeight: 21 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  action: { backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12 },
  actionText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  uploading: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 14 },
  uploadingText: { color: colors.primary, fontWeight: '600' },
  error: { color: colors.danger, marginTop: 12, fontSize: 14 },

  section: { fontSize: 18, fontWeight: '800', color: colors.text, marginTop: 28, marginBottom: 12 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  tile: { width: '48%', flexGrow: 1, backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 },
  tileText: { fontWeight: '700', color: colors.text, fontSize: 15 },
  soon: { color: colors.muted, fontSize: 12, marginTop: 4 },

  empty: { color: colors.muted, lineHeight: 22 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.soft },
  badge: { width: 46, height: 46, borderRadius: 12, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' },
  badgeText: { color: colors.primary, fontWeight: '800', fontSize: 12 },
  itemName: { fontWeight: '600', color: colors.text, fontSize: 15 },
  itemMeta: { color: colors.muted, fontSize: 13, marginTop: 2 },
  delete: { color: colors.danger, fontWeight: '600', fontSize: 14 },
});
