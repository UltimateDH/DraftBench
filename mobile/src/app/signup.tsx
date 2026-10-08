import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { Link } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '@/context/AuthContext';
import { AuthShell, ErrorText, Field, PrimaryButton } from '@/components/AuthUI';
import { Photo } from '@/lib/api';
import { colors } from '@/lib/theme';

export default function Signup() {
  const { signUp } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const pickPhoto = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.7,
    });
    if (res.canceled) return;
    const a = res.assets[0];
    const ext = (a.uri.split('.').pop() ?? 'jpg').split('?')[0].toLowerCase();
    setPhoto({ uri: a.uri, name: `profile.${ext}`, type: a.mimeType ?? `image/${ext === 'jpg' ? 'jpeg' : ext}` });
  };

  const submit = async () => {
    if (username.trim().length < 3) return setError('Username must be at least 3 characters.');
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError('Enter a valid email address.');
    if (password.length < 8) return setError('Password must be at least 8 characters.');
    setError('');
    setLoading(true);
    try {
      await signUp({ username: username.trim(), email: email.trim(), password, photo });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell compact title="Create your account" subtitle="It takes less than a minute.">
      <Pressable onPress={pickPhoto} style={s.avatarWrap}>
        {photo ? (
          <Image source={{ uri: photo.uri }} style={s.avatar} />
        ) : (
          <View style={[s.avatar, s.avatarEmpty]}><Text style={s.avatarPlus}>+</Text></View>
        )}
        <Text style={s.avatarText}>{photo ? 'Change photo' : 'Add profile photo (optional)'}</Text>
      </Pressable>
      <Field label="Username" value={username} onChangeText={setUsername} textContentType="username" />
      <Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" textContentType="emailAddress" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry textContentType="newPassword" />
      <ErrorText message={error} />
      <PrimaryButton title="Create account" onPress={submit} loading={loading} />
      <Text style={s.switch}>
        Already registered? <Link href="/login" style={s.link}>Log in</Link>
      </Text>
    </AuthShell>
  );
}

const s = StyleSheet.create({
  avatarWrap: { alignItems: 'center', marginBottom: 22 },
  avatar: { width: 88, height: 88, borderRadius: 44, borderWidth: 3, borderColor: colors.soft },
  avatarEmpty: { backgroundColor: colors.soft, borderColor: colors.border, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center' },
  avatarPlus: { fontSize: 34, color: colors.primary, marginTop: -2 },
  avatarText: { marginTop: 8, color: colors.primary, fontWeight: '600', fontSize: 14 },
  switch: { textAlign: 'center', marginTop: 22, color: colors.muted, fontSize: 15 },
  link: { color: colors.primary, fontWeight: '700' },
});